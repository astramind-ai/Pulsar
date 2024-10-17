import asyncio
import os
import shutil
import warnings
from typing import Union

from fastapi import APIRouter, Depends, Form, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from huggingface_hub.utils import RepositoryNotFoundError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse
from vllm.usage.usage_lib import UsageContext

from app.core.engine import create_serving_instances
from app.db.auth.auth_db import get_current_user, get_last_model_lora, \
    set_last_model_lora
from app.db.lora.lora_db import get_lora_list, hash_lora_str_id, get_lora
from app.db.ml_models.model_db import get_model_list, download_model_api_, \
    create_model_async, add_model_to_db, edit_model_async, \
    delete_model_async, change_model_id_and_owner, get_model_path_or_url, get_model
from app.db.model.auth import User
from app.db.model.ml_model import Model
from app.hijacks.vllm import ExtendedAsyncCompleteServerArgs
from app.middlewares.model_loader_block import set_block_requests
from app.utils.database.get import get_db
from app.utils.database.images import save_image, delete_image
from app.utils.formatting.pydantic.request import ImageRequest
from app.utils.log import setup_custom_logger
from app.utils.formatting.pydantic.privacy import PrivacyOptions
from app.utils.server.image_fetch import get_image
from app.utils.server.restarter import restart

warnings.filterwarnings("ignore", category=UserWarning, message=".*has conflict with protected namespace *")

router = APIRouter()

logger = setup_custom_logger(__name__)


@router.get("/model_image/{image_name}")
async def get_router_image(image_name: str):
    image_request = ImageRequest(image_name=image_name)
    return await get_image(image_request)


@router.get("/model/list")
async def show_available_models(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)):
    models = await get_model_list(db)
    model_w_loras = {}
    non_f_model = {}
    for model in models:
        if model.working:
            loras = await get_lora_list(current_user, db, model.base_architecture)
            model_w_loras[model.name] = {
                "name": model.name, "path": model.path,
                "id": model.id, "image": model.image,
                "model_description": model.description,
                "model_url": model.url, "owner": model.owner,
                "model_speed": model.speed_value,
                "model_architecture": model.base_architecture,
                "versions": model.variants,
                "loras": [lora.name for lora in loras]
            }
        else:
            non_f_model[model.name] = {"name": model.name, "path": model.path,
                                       "versions": model.variants,
                                       "id": model.id, "image": model.image,
                                       "model_description": model.description,
                                       "model_architecture": model.base_architecture,
                                       "model_url": model.url, "owner": model.owner
                                       }

    return JSONResponse(content={"models": model_w_loras, "non_functional_models": non_f_model})


@router.get("/model/loaded")
async def show_loaded_model(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.core.engine import openai_serving_chat, is_lora_enabled, is_model_vision, images_per_prompt
    model_name = openai_serving_chat.engine_client.engine.get_model_config().model # noqa
    last_conf = await get_last_model_lora(db, current_user)

    if last_conf['model'] != model_name:
        await set_last_model_lora(db, current_user, model_id=model_name)
    model = await get_model(db, url=model_name)
    if not model:
        raise HTTPException(detail="Model not found", status_code=404)
    model_vars = vars(model)
    final_dict = {}
    for var in model_vars:
        if var not in {'_sa_instance_state', 'chats', 'messages', 'completions', 'users', 'loras', 'metadata',
                       'registry'}:
            final_dict[var] = model_vars[var]
    lora = None
    if is_lora_enabled:
        loras = openai_serving_chat.engine_client.engine.list_loras() # noqa

        lora_url = last_conf['lora'] if any([lora == await hash_lora_str_id(last_conf['lora'])
                                             for lora in loras if lora is not None]) else None
        # we return the last lora if it still loaded

        if lora_url:
            lora_item = await get_lora(lora_url=lora_url, db=db)
            if lora_item:
                lora = {"name": lora_item.name, "image": lora_item.image,
                        "base_architecture": lora_item.base_architecture,
                        "url": lora_item.url, "description": lora_item.description,
                        "owner": lora_item.owner}
    return JSONResponse(content={"model": final_dict, "lora": lora, "is_lora_enabled": is_lora_enabled,
                                 'is_vision': is_model_vision, "images_per_prompt": images_per_prompt})


@router.post("/model/load")
async def load_model(background_tasks: BackgroundTasks, model_url: str = Form(...), model_variant: str = Form(None),
                     db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.core.engine import (openai_serving_chat,
                                 delete_engine_model_from_vram, initialize_engine, async_engine_args)
    try:

        old_conf = await openai_serving_chat.engine_client.get_model_config()

        if model_url == old_conf.model:
            raise HTTPException(detail="Model already loaded", status_code=409)

        is_model_predownloaded = (await db.execute(select(Model).where(Model.url == model_url))).scalars().first()

        set_block_requests(True)

        # Ensure that both engines are not currently running any tasks
        while openai_serving_chat.engine_client.engine.has_unfinished_requests(): # noqa
            await asyncio.sleep(0.1)

        if not is_model_predownloaded:
            return JSONResponse(content={"error": "Model not found, is it installed?"}, status_code=404)

        # create a restoration server configuration
        server_conf = ExtendedAsyncCompleteServerArgs.from_yaml("last.yml")
        server_conf.gpu_memory_utilization = async_engine_args.gpu_memory_utilization
        # here because otherwise the gpu memory utilization would be calculated with the model still in vram
        model_path = await get_model_path_or_url(is_model_predownloaded, model_variant)
        # try to load the new model, if it fails reload the previous model
        try:
            delete_engine_model_from_vram()

            server_conf.model = model_path
            server_conf.tokenizer = model_url
            server_conf.served_model_name = [model_url]
            await initialize_engine(server_conf.get_async_eng_args(), UsageContext.OPENAI_API_SERVER)
            create_serving_instances(server_conf.served_model_name, server_conf)

            server_conf.save_to_yaml()
            set_block_requests(False)

        except Exception as e:
            background_tasks.add_task(restart(server_conf, True))
            return JSONResponse(
                content={"status": f"The model you select run into errors ({e}), defaulted back to the orignal model"},
                status_code=205)

        await set_last_model_lora(db, current_user, model_id=is_model_predownloaded.url)
        return JSONResponse(content={"status": "Model loaded successfully"}, status_code=200)
    except RepositoryNotFoundError:
        set_block_requests(False)
        return JSONResponse(content={
            "error": "Model not found, please double check the repo name and if you have the right permissions"},
            status_code=404)
    except HTTPException as e:
        raise e
    except Exception as e:
        set_block_requests(False)
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.post("/model/create")
async def create_model(
        background_tasks: BackgroundTasks,
        model_name: str = Form(...),
        model_description: str = Form(...),
        model_image: Union[UploadFile, str] = Form(None),
        model_url: str = Form(...),
        model_tags: str = Form(None),
        privacy_settings: PrivacyOptions = Form(...),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)):
    model = await get_model(db, url=model_url)
    new_filename = ''
    if model_image:
        new_filename = await save_image(current_user, model_image)
    if model:
        # if we added the model via db the db init flow we need to fetch the online id and owner
        if privacy_settings.value != "local":
            try:
                json_repsonse = await create_model_async(db, name=model_name, tags=model_tags,
                                                         description=model_description,
                                                         image=model_image,
                                                         is_private=True if privacy_settings.value == "private"
                                                         else False,
                                                         url=model_url)
                model.id = json_repsonse['id']
                model.owner = json_repsonse['owner']
                model.description = model_description
                model.name = model_name
                model.image = new_filename
                await db.commit()
                return {"status": "Model created successfully"}
            except Exception as e:
                raise HTTPException(status_code=500, detail="Model creation failed, " + str(e))
        else:
            raise HTTPException(status_code=409, detail="Model url already exists")

    try:
        model = await add_model_to_db(db, model_name, model_description, model_image, new_filename, model_url,
                                      privacy_settings, current_user, model_tags, background_tasks)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Model creation failed, " + str(e))

    db.add(model)
    await db.commit()
    await db.refresh(model)
    return {"status": "Model created successfully"}


@router.put("/model/edit")
async def edit_model(ml_model_id: str = Form(...),
                     ml_model_name: str = Form(None),
                     ml_model_description: str = Form(None),
                     ml_model_image: Union[UploadFile, str] = Form(None),
                     privacy_settings: PrivacyOptions = Form(None),
                     online_id: str = Form(None),
                     tags: str = Form(None),
                     current_user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    model = await get_model(db, model_id=ml_model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    if ml_model_description:
        model.description = ml_model_description
    if ml_model_name:
        model.name = ml_model_name
    if ml_model_image:
        image_filename = await save_image(current_user, ml_model_image)
        await delete_image(model)
        model.image = image_filename
    if online_id:
        model.id = online_id
    db.add(model)
    await db.commit()
    if privacy_settings and privacy_settings.value != "local":
        try:
            await edit_model_async(db, model.name, tags, ml_model_description, ml_model_image,
                                   privacy_settings.value == 'private',
                                   ml_model_id)
        except Exception as e:
            return JSONResponse(content={"message": f"Error pushing edited model online: {str(e)}"},
                                status_code=500)

    return JSONResponse(content={"message": "Model edited successfully"})


@router.delete("/model/delete")
async def delete_model(ml_model_id: str = Form(...),
                       also_delete_loras: bool = Form(False),
                       also_delete_online: bool = Form(False),
                       current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    if also_delete_online:
        await delete_model_async(db, ml_model_id)

    model = await get_model(db, model_id=ml_model_id)
    if not model and not also_delete_online:
        raise HTTPException(status_code=404, detail="Model not found")
    elif not model:
        return JSONResponse(content={"message": "Model deleted successfully"}, status_code=200)
    # get all loras that use this model
    loras_of_model = (await get_lora_list(current_user, db,
                                          model.base_architecture)) if also_delete_loras else []
    if len(model.users) < 2:
        items = [model]
        await db.delete(model)
    else:
        items = []
        model.users = [user for user in model.users if user.id != current_user.id]

    if also_delete_loras:
        if len(loras_of_model) > 0:  # delete all loras that use this model from the database
            for lora in loras_of_model:
                if len(lora.users) < 2:
                    items.append(lora)
                else:
                    lora.users = [user for user in lora.users if user.id != current_user.id]
                await db.delete(lora)
    try:
        for item in items:  # delete all files associated with the model
            if os.path.exists(item.path):
                shutil.rmtree(item.path)
                await delete_image(item)

        await db.commit()

        return JSONResponse({"message": "Model deleted successfully"}, 200)

    except Exception as e:
        await db.rollback()
        return JSONResponse({"error": str(e)}, 500)


@router.post("/model/download")
async def download_model_api(
        background_tasks: BackgroundTasks,
        model_id: str = Form(...),
        model: str = Form(...),
        tags: str = Form(None),
        model_base_architecture: str = Form(...),
        model_description: str = Form(None),
        file_variant: str = Form(None),
        model_url: str = Form(...),
        image: Union[UploadFile, str] = Form(None),
        owner: str = Form(None),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)):
    return await download_model_api_(model_id=model_id, model_arch=model_base_architecture, model_name=model,
                                     model_url=model_url, model_description=model_description, owner=owner, image=image,
                                     current_user=current_user, file_variant=file_variant, tags=tags,
                                     db=db, background_tasks=background_tasks)


@router.post("/model/push_online")
async def push_model_online(
        model_name: str = Form(...),
        model_local_id: str = Form(...),
        model_description: str = Form(None),
        tags: str = Form(None),
        model_url: str = Form(...),
        image: Union[UploadFile, str] = Form(None),
        is_private: bool = Form(False),
        is_new_item: bool = Form(False),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)):
    if not is_new_item:
        await edit_model_async(db, model_name, tags, model_description, image, is_private, model_local_id)
    else:
        try:
            response = await create_model_async(db, model_name, model_description, image, model_url, is_private, tags)
            await change_model_id_and_owner(db, model_local_id,
                                            response['id'], response['owner'],
                                            current_user)

        except Exception as e:
            return JSONResponse(content={"message": f"Error pushing model online: {str(e)}"}, status_code=500)
    return JSONResponse(content={"message": "Model pushed successfully"})
