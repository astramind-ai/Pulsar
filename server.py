from dotenv import load_dotenv, set_key

load_dotenv()

from app.utils.definitions import CONF_FILE
from app.utils.formatting.pydantic.request import EnvVar
from app.utils.server.config import generate_yaml_entry
from app.utils.server.restarter import restart

import asyncio
import importlib
import inspect
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Set, Optional

import fastapi
import uvicorn
import vllm
import vllm.envs as envs
from fastapi import Request, Depends, BackgroundTasks
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import make_asgi_app
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.routing import Mount
from vllm import AsyncLLMEngine
from vllm.entrypoints.openai.cli_args import make_arg_parser
from vllm.usage.usage_lib import UsageContext
from vllm.utils import FlexibleArgumentParser

from app.api.authorization import router as auth_router
from app.api.chats import router as chat_router
from app.api.loras import router as lora_router
from app.api.models import router as model_router
from app.api.personalities import router as personalitys_router
from app.api.personas import router as persona_router
from app.api.reverse_proxy import router as reverse_proxy_router
from app.api.open_ai import router as openai_router, load_serving_entrypoints

from app.core.engine import initialize_engine, create_serving_instances
from app.core.error_checking.health_monitoring import setup_server_monitoring
from app.db.auth.auth_db import get_current_user, ensure_local_request
from app.db.db_setup import init_db
from app.db.lora.lora_db import get_lora_list
from app.db.model.auth import User
from app.db.personality.personality_db import get_user_personality_list
from app.db.tokens.db_token import set_local_url_online
from app.hijacks.openai import ExtendedOpenAIServingChat
from app.hijacks.vllm import astra_parser_wrapper, ExtendedAsyncCompleteServerArgs
from app.middlewares.model_loader_block import BlockRequestsMiddleware
from app.tunneling.tunnel_manager import start_tunnel_after_server
from app.utils.database.get import get_db
from app.utils.log import setup_custom_logger
from app.utils.server.updater import check_and_update, get_current_version

openai_serving_chat: Optional[ExtendedOpenAIServingChat] = None
async_engine: Optional[AsyncLLMEngine] = None
(online_auth_token, localtunnel_url) = None, None

CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), "configs")
TIMEOUT_KEEP_ALIVE = 5  # seconds
logger = setup_custom_logger(__name__)
logging.basicConfig()
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARN)



_running_tasks: Set[asyncio.Task] = set()

resource_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    global openai_serving_chat, async_engine, global_username, global_email, global_pfp # noqa

    async def _force_log():
        while True:
            await asyncio.sleep(10)
            await async_engine.do_log_stats()

    from app.core.engine import openai_serving_chat as _openai_serving_chat, async_engine as _async_engine
    openai_serving_chat, async_engine = _openai_serving_chat, _async_engine

    monitor = await setup_server_monitoring()    # start the health monitoring


    await init_db()

    if eng_args.disable_log_stats:
        task = asyncio.create_task(_force_log())
        _running_tasks.add(task)
        task.add_done_callback(_running_tasks.remove)

    yield

    monitor.stop_monitoring()


app = fastapi.FastAPI(lifespan=lifespan)
app.add_middleware(BlockRequestsMiddleware) # Block requests when new model is loading
# Add prometheus asgi middleware to route /metrics requests
route = Mount("/metrics", make_asgi_app())
# Workaround for 307 Redirect for /metrics
route.path_regex = re.compile('^/metrics(?P<path>.*)$')

# Add the routes to the app
app.routes.append(route)
app.include_router(auth_router)
app.include_router(personalitys_router)
#app.include_router(persona_router)
app.include_router(model_router)
app.include_router(lora_router)
app.include_router(chat_router)
app.include_router(reverse_proxy_router)
app.include_router(openai_router)


def parse_args():
    parser = FlexibleArgumentParser(
        description="Pulsar Application backed by a vLLM OpenAI-Compatible RESTful API server.")
    parser = make_arg_parser(parser)
    parser = astra_parser_wrapper(parser)
    parsed_args = parser.parse_args()
    parsed_args.enforce_eager = True
    return parsed_args


async def set_online_url(url: str):
    global localtunnel_url
    localtunnel_url = url

    status = await set_local_url_online(url)
    if status == 200:
        return JSONResponse(content={"message": "Online URL set."})
    else:
        return JSONResponse(content={"message": "Error setting online URL."}, status_code=status)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_, exc):
    err = openai_serving_chat.create_error_response(message=str(exc))
    return JSONResponse(err.model_dump(), status_code=HTTPStatus.BAD_REQUEST)


@app.get("/health")
async def health() -> Response:
    """Health check."""
    await openai_serving_chat.engine_client.check_health()
    return Response(status_code=200)

@app.post("/set_env_var")
async def set_env_variable(background_tasks: BackgroundTasks, env_var: EnvVar, is_local = Depends(ensure_local_request)):
    try:
        # Obtain the path to the .env file
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        set_key(env_path, env_var.key, env_var.value)

        if env_var.reboot_required:
            background_tasks.add_task(restart())

        return JSONResponse(content={"message": f"Environment variable {env_var.key} set successfully"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set environment variable: {str(e)}")


@app.get("/get_app_init_config")
async def get_app_init_config(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.db.ml_models.model_db import get_model_list
    from app.api.reverse_proxy import global_username, global_email, global_pfp
    excluded_attributes = {'loras', 'chats', 'completions', 'messages', 'models', 'users', '_sa_instance_state'}

    # Get general engine conf
    server_args = ExtendedAsyncCompleteServerArgs.from_yaml(CONF_FILE)
    server_args.host = localtunnel_url
    # Get Public available models & loras
    models = await get_model_list(db)
    # get personality list
    personalities = await get_user_personality_list(db, current_user.id)
    # get lora list
    loras = await get_lora_list(current_user, db)
    # get personas
    #personas = await get_user_persona_list(db, current_user.id)
    # List comprehensions
    models = [{key: getattr(model, key) for key in vars(model).keys() if key not in excluded_attributes} for model in
              models]
    personalities = [
        {key: getattr(personality, key) for key in vars(personality).keys() if key not in excluded_attributes} for
        personality in personalities]
    loras = [{key: getattr(lora, key) for key in vars(lora).keys() if key not in excluded_attributes} for lora in loras]
    #personas = [{key: getattr(persona, key) for key in vars(persona).keys() if key not in excluded_attributes} for
    #            persona in personas]

    # generate a qr (?)
    conf = {"server_args": vars(server_args), "models": models,
            "personalities": personalities, "loras": loras,
            #"personas": personas,
            "username": global_username,
            "hf_token": os.environ.get("PULSAR_HF_TOKEN", None),
            "email": global_email, "pfp": global_pfp
            }
    return JSONResponse(content=conf)


@app.get("/versions")
async def show_version():
    ver = {"pulsar_version": get_current_version(), "vllm_version": vllm.__version__}
    return JSONResponse(content=ver)


async def main():
    check_and_update()
    global eng_args
    if not os.path.exists(os.path.join(CONFIG_FILE_PATH, CONF_FILE)):
        generate_yaml_entry(os.path.join(CONFIG_FILE_PATH, CONF_FILE))

    server_args = ExtendedAsyncCompleteServerArgs.from_yaml(CONF_FILE)

    eng_args = server_args.get_async_eng_args()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=server_args.allowed_origins,
        allow_credentials=server_args.allow_credentials,
        allow_methods=server_args.allowed_methods,
        allow_headers=server_args.allowed_headers,
    )

    for middleware in server_args.middleware:
        module_path, object_name = middleware.rsplit(".", 1)
        imported = getattr(importlib.import_module(module_path), object_name)
        if inspect.isclass(imported):
            app.add_middleware(imported)
        elif inspect.iscoroutinefunction(imported):
            app.middleware("http")(imported)
        else:
            raise ValueError(f"Invalid middleware {middleware}. Must be a function or a class.")

    logger.info("vLLM API server version %s", vllm.__version__)
    logger.info("server args: %s", server_args)

    # Initialize and passing the engine to the global variable
    await initialize_engine(eng_args, UsageContext.OPENAI_API_SERVER)
    create_serving_instances(eng_args.served_model_name, server_args)
    load_serving_entrypoints()
    config = uvicorn.Config(
        app,  # Assicurati che questo corrisponda al nome del tuo file e dell'istanza FastAPI
        host=server_args.host,
        port=server_args.port,
        workers=(os.cpu_count() or 1) * 2 + 1,  # Numero di worker basato sulle CPU disponibili
        log_level=server_args.uvicorn_log_level,
        timeout_keep_alive=TIMEOUT_KEEP_ALIVE,
        ssl_keyfile=server_args.ssl_keyfile,
        ssl_certfile=server_args.ssl_certfile,
        ssl_ca_certs=server_args.ssl_ca_certs,
        ssl_cert_reqs=server_args.ssl_cert_reqs,
        limit_concurrency=1000,  # Imposta un limite alto per la concorrenza
        limit_max_requests=10000)  # Imposta un limite alto per le richieste massime)
    server = uvicorn.Server(config)

    # Start the server in a separate task
    server_task = asyncio.create_task(server.serve())

    # Wait for the server to start
    while not server.started:
        await asyncio.sleep(0.1)

    # Start tunneling after the server is up
    await start_tunnel_after_server(server_args)

    # Wait for the server task to complete
    await server_task


if __name__ == "__main__":
    asyncio.run(main())
