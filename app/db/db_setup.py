import os
import secrets
import string
import uuid

from dotenv import set_key
from sqlalchemy import select, AsyncAdaptedQueuePool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.db.migration.migrate import run_migrations
from app.db.model.base import Base
from app.db.model.lora import LoRA
from app.db.model.ml_model import Model
from app.db.model.token import Token
from app.utils.models.gguf_util import extract_gguf_info_local
from app.utils.log import setup_custom_logger
from app.utils.models.hf_downloader import check_file_in_huggingface_repo
from app.utils.models.list_model import list_models_paths_in_hf_cache, list_loras_hf
from app.utils.definitions import MODEL_PATHS, DATABASE_URL

logger = setup_custom_logger(__name__)


engine = create_async_engine(DATABASE_URL, echo=False,
                             poolclass=AsyncAdaptedQueuePool,
                             pool_size=20,
                             max_overflow=40,
                             pool_pre_ping=True,
                             pool_recycle=360
                             )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession, expire_on_commit=False)


async def post_creation_task():
    from app.db.ml_models.model_db import get_model_id_from_online
    from app.db.lora.lora_db import get_lora_id_from_online
    from app.db.ml_models.model_db import get_model
    from app.utils.models.model_paths import get_hf_path
    from app.db.lora.lora_db import get_orignal_model_name

    try:
        async with SessionLocal() as session:
            models = await list_models_paths_in_hf_cache()
            local_model_list = (await session.execute(select(Model.url))).scalars().all()
            model_to_profile = [model for model in models if
                                (model if isinstance(model, str) else model[0]) not in local_model_list]

            for model in model_to_profile:

                if isinstance(model, list):  # this is for gguf models and possibly exl2 in the future which have more
                    # than one file per repo
                    if any(['gguf' in model for model in model[1]]):
                        base_arch = f"gguf@{extract_gguf_info_local(model[1][0])['metadata']['general.architecture']}"
                    model_id = uuid.uuid4().hex
                    paths = {variant_path.split('/')[-1]: variant_path for variant_path in model[1]}
                    variants = ','.join(paths.keys())
                    model = Model(id=model_id, url=model[0], owner='everyone', name=model[0].split("/")[-1],
                                  path=str(paths), working=True,
                                  description="Model was pre downloaded from Hugging Face",
                                  base_architecture=base_arch,
                                  variants=variants,
                                  )
                    session.add(model)

                elif isinstance(model, str):
                    model_url = model
                    try:
                        model_id = await get_model_id_from_online(session, model_url.split("/")[-1],
                                                                  "Model added automatically",
                                                                  None, model_url, False)
                    except Exception as e:
                        if '401 Unauthorized' in str(e):
                            logger.error(f"You aren't logged in!: {e}")
                        else:
                            logger.error(f"Error while getting model id from online: {e}")
                        model_id = uuid.uuid4().hex
                    try:

                        # speed = get_speed(eng_args)
                        base_arch = await check_file_in_huggingface_repo(model_url, "config.json")
                        base_path = get_hf_path(model_url)
                        model = Model(id=model_id, url=model_url, owner='everyone', name=model_url.split("/")[-1],
                                      path=os.path.join(MODEL_PATHS, await base_path),
                                      # speed_value=await speed, working=True,
                                      description="Model was pre downloaded from Hugging Face",
                                      base_architecture='Unknown' if not base_arch else base_arch)

                        session.add(model)
                    except Exception as e:
                        logger.error(f"Error while adding model {model_url} to the database: {e}")
                        model = Model(id=model_id, url=model_url, owner='everyone', name=model_url.split("/")[-1],
                                      path=os.path.join(MODEL_PATHS, await get_hf_path(model_url)),
                                      working=False,
                                      description=str(e), base_architecture="CausalLM")
                        session.add(model)

            loras = list_loras_hf()
            local_lora_list = (await session.execute(select(LoRA.url))).scalars().all()
            loras_to_add = [lora for lora in await loras if lora not in local_lora_list]
            for lora_url in loras_to_add:
                original_model_name = await get_orignal_model_name(lora_url)
                if original_model_name:
                    model = await get_model(session, original_model_name)
                else:
                    model = None
                try:
                    lora_id = await get_lora_id_from_online(session, lora_url.split("/")[-1],
                                                            "Model added automatically",
                                                            None, model.id, lora_url, False)
                except Exception as e:
                    if '401 Unauthorized' in str(e):
                        logger.error(f"You aren't logged in!: {e}")
                    else:
                        logger.error(f"Error while getting LoRA id from online: {e}")
                    lora_id = uuid.uuid4().hex
                try:
                    lora = LoRA(id=lora_id,
                                name=lora_url.split("/")[-1], url=lora_url, owner='everyone',
                                path=os.path.join(MODEL_PATHS, await get_hf_path(lora_url)),
                                base_architecture=await check_file_in_huggingface_repo(lora_url, "adapter_config.json"))
                    session.add(lora)
                except Exception as e:
                    logger.error(f"Error while adding LoRA {lora_url} to the database: {e}")
                    lora = LoRA(id=lora_id, name=lora_url.split("/")[-1], url=lora_url, owner='everyone',
                                path=os.path.join(MODEL_PATHS, await get_hf_path(lora_url)),
                                description=str(e))
                    session.add(lora)
            await session.commit()

    except Exception as e:
        logger.error(f"Error in post_creation_task: {e}")
    finally:
        logger.info("Post creation task finished")


async def ensure_default_token(session):
    # look for the default token
    result = await session.execute(select(Token).filter_by(id=1))
    token = result.scalars().first()
    if not token:
        # if not, create a default token
        token = Token(id=1)
        session.add(token)
        await session.commit()


async def init_db():
    try:
        run_migrations(DATABASE_URL.replace("+asyncpg", ""),
                       os.path.join(os.path.dirname(__file__), "migration", "alembic.ini"))
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await post_creation_task()
        async with SessionLocal() as session:
            await ensure_default_token(session)
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise
