import os
import shutil
import uuid
from typing import Union

from fastapi import APIRouter, Depends, Form, UploadFile, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse
from vllm.lora.request import LoRARequest

from app.db.auth.auth_db import get_current_user, set_last_model_lora, get_user
from app.db.lora.lora_db import get_lora_list, get_lora, get_user_lora, hash_lora_str_id, is_lora_correct, \
    edit_lora_async, create_lora_async, delete_lora_async, get_user_lora_by_url, change_lora_id_and_owner
from app.utils.models.model_paths import get_hf_path
from app.db.model.auth import User
from app.db.model.lora import LoRA
from app.utils.database.get import get_db
from app.utils.database.images import save_image, delete_image
from app.utils.formatting.pydantic.request import ImageRequest
from app.utils.log import setup_custom_logger
from app.utils.models.hf_downloader import download_model_async, check_file_in_huggingface_repo
from app.utils.models.list_model import list_loras_hf
from app.utils.formatting.pydantic.privacy import PrivacyOptions
from app.utils.server.image_fetch import get_image
from app.utils.definitions import UPLOAD_DIRECTORY, MODEL_PATHS
router = APIRouter()

logger = setup_custom_logger(__name__)

lora_chat_template_dict = {}

@router.get("/lora_image/{image_name}")
async def get_router_image(image_name: str):
    image_request = ImageRequest(image_name=image_name)
    return await get_image(image_request)


@router.post("/lora/download")
async def download_lora(lora_id: str = Form(...),
                        lora_name: str = Form(...),
                        lora_description: str = Form(...),
                        lora_image: Union[UploadFile, str] = Form(...),
                        lora_url: str = Form(...),
                        owner: str = Form(...),
                        base_architecture: str = Form(None),
                        current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    lora = await get_lora(db, lora_url)
    image_name = await save_image(current_user, lora_image)
    if lora:
        if lora.id != lora_id and lora.owner == 'everyone':
            lora.id = lora_id
            lora.description = lora_description
            lora.name = lora_name

            lora.image = image_name
            lora.owner = owner



            if current_user not in lora.users:

                db_user = await get_user(db, current_user.name)
                lora.users.append(db_user)
            else:
                return JSONResponse(content={"message": "You already have this LoRA"})
        else:
            if current_user not in lora.users:
                db_user = await get_user(db, current_user.name)
                lora.users.append(db_user)
            else:
                return JSONResponse(content={"message": "You already have this LoRA"})
        await db.commit()
        return JSONResponse(content={"message": "LoRA downloaded successfully"})
    # If it's new, download it
    try:
        await download_model_async(lora_url)

        lora = LoRA(id=lora_id, name=lora_name.split("/")[-1],
                    url=lora_url, path=os.path.join(MODEL_PATHS, await get_hf_path(lora_url)),
                    description=lora_description, users=[current_user], base_architecture=base_architecture,
                    image=image_name,
                    owner=owner)
        db.add(lora)
        await db.commit()
        return JSONResponse(content={"message": "LoRA downloaded successfully"})
    except Exception as e:
        raise HTTPException(detail=f"Error downloading LoRA: {str(e)}", status_code=500)


@router.put("/lora/edit")
async def lora_edit(
        lora_id: str = Form(...),
        lora_name: str = Form(None),
        tags: str = Form(None),
        lora_description: str = Form(None),
        image: Union[UploadFile, str] = Form(None),
        privacy_settings: PrivacyOptions = Form(None),
        online_id: str = Form(None),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)):
    lora = await get_user_lora(current_user, db, lora_id)
    if not lora:
        raise HTTPException(detail="LoRA not found", status_code=404)

    try:
        if lora_name:
            lora.name = lora_name

        if lora_description:
            lora.description = lora_description
        if image:
            new_filename = await save_image(current_user, image)
            await delete_image(lora)
            lora.image = new_filename
        if online_id:
            lora.id = online_id
        db.add(lora)
        await db.commit()
        if privacy_settings and privacy_settings.value != "local":
            try:
                await edit_lora_async(db, tags=tags, name=lora_name, description=lora_description, image=image,
                                      is_private=True if privacy_settings.value == "private" else False,
                                      lora_id=lora.id)
            except Exception as e:
                raise HTTPException(detail=f"Error pushing edited model online: {str(e)}",
                                    status_code=500)
    except Exception as e:
        await db.rollback()
        raise HTTPException(detail=f"Error editing model: {str(e)}", status_code=500)
    return JSONResponse(content={"message": "Model edited successfully"})


@router.delete("/lora/delete")
async def delete_lora(lora_id: str = Form(...),
                      also_delete_online: bool = Form(False),
                      current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    if also_delete_online:
        await delete_lora_async(db, lora_id)

    lora = await get_user_lora(current_user, db, lora_id)
    if not lora and not also_delete_online:
        return HTTPException(detail="Model not found are you sure you have the permissions to see this model?",
                             status_code=404)
    elif not lora:
        return JSONResponse(content={"message": "Model deleted successfully"})
    try:
        if len(lora.users) < 2:
            await delete_image(lora)
            await db.delete(lora)
            if os.path.exists(lora.path):
                shutil.rmtree(lora.path)
        else:
            lora.users = [user for user in lora.users if user.id != current_user.id]

    except Exception as e:
        await db.rollback()
        raise HTTPException(detail=f"Error deleting model: {str(e)}", status_code=500)
    await db.commit()

    return JSONResponse(content={"message": "Model deleted successfully"})


@router.post("/lora/create")
async def create_lora(lora_name: str = Form(...),
                      lora_url: str = Form(...),
                      lora_tags: str = Form(None),
                      lora_description: str = Form(...),
                      lora_image: Union[UploadFile, str] = Form(None),
                      privacy_settings: PrivacyOptions = Form(...),
                      hf_model_id: str = Form(...),
                      current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    lora = await get_user_lora_by_url(current_user, db, lora_url)
    if lora:
        if privacy_settings.value != "local":
            try:
                _ = await create_lora_async(db, tags=lora_tags, name=lora_name,
                                            description=lora_description,
                                            image=lora_image,
                                            is_private=True if privacy_settings.value == "private" else False,
                                            model_id=hf_model_id, url=lora_url)
                return JSONResponse(content={"message": "LoRA already exists locally, pushed online successfully"})
            except Exception as e:
                raise HTTPException(status_code=500, detail="LoRA creation failed, " + str(e))
        else:
            raise HTTPException(status_code=409, detail="LoRA url already exists")
    image_name = await save_image(current_user, lora_image)
    await download_model_async(lora_url)
    lora_path = os.path.join(MODEL_PATHS, await get_hf_path(
        lora_url))
    base_architecture = await check_file_in_huggingface_repo(lora_url, "adapter_config.json")
    if not base_architecture:
        raise HTTPException(status_code=500,
                            detail="LoRA architecture could not be inferred, "
                                   "please check if the model is a correct adapter model.")
    if privacy_settings.value != "local":
        try:
            json_response = await create_lora_async(db, tags=lora_tags, name=lora_name,
                                                    description=lora_description,
                                                    image=lora_image,
                                                    is_private=True if privacy_settings.value == "private" else False,
                                                    model_id=hf_model_id, url=lora_url)
        except Exception as e:
            raise HTTPException(status_code=500, detail="LoRA creation failed, " + str(e))
        # use the id returned form the call
        if not json_response.get('owner', None):
            raise HTTPException(status_code=500,
                                detail="LoRA creation failed, no ID returned from the main server")
        lora = LoRA(id=json_response['id'], name=lora_name, path=lora_path,
                    owner=json_response['owner'], image=image_name, base_architecture=base_architecture,
                    url=lora_url, description=lora_description,
                    users=[current_user])
    else:

        lora = LoRA(id=uuid.uuid4().hex, name=lora_name, path=lora_path,
                    owner=current_user.name, image=image_name, base_architecture=base_architecture,
                    url=lora_url, description=lora_description,
                    users=[current_user])

    db.add(lora)
    await db.commit()
    await db.refresh(lora)
    return {"status": "LoRA created successfully"}


@router.get("/lora/list")
async def show_available_models(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    loras_list = await get_lora_list(current_user, db)
    loras_final_list = []
    for lora in loras_list:
        loras = {}
        for var in vars(lora):
            if var != "users" and var != "model" and var != "chats" and var != "completions" and var != "messages":
                loras[var] = getattr(lora, var)
        loras_final_list.append(loras)

    return {"loras": loras_final_list}


@router.post("/lora/load")
async def load_model(lora_url: str = Form(...),
                     current_user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    global lora_chat_template_dict

    lora = await get_user_lora_by_url(current_user, db, lora_url)
    if not lora:
        raise HTTPException(detail="LoRA not found", status_code=404)
    is_correct, error_maybe_template = await is_lora_correct(lora, db)
    if not is_correct:
        raise HTTPException(detail=error_maybe_template, status_code=404)

    lora_int_id = await hash_lora_str_id(lora.url)
    await set_last_model_lora(db, current_user, lora_id=lora.url)
    lora_request = LoRARequest(lora_int_id=lora_int_id, lora_name=lora.url,
                               lora_path=await list_loras_hf(lora.path))

    try:
        from app.core.engine import openai_serving_chat
        lora_list = {lora.lora_int_id for lora in openai_serving_chat.lora_requests}
        if lora_int_id in lora_list:
            return JSONResponse(content={"message": "Model already loaded"}, status_code=200)
        is_lora_loaded = openai_serving_chat.engine_client.engine.add_lora(lora_request)
        if is_lora_loaded:
            openai_serving_chat.lora_requests.append(lora_request)
    except Exception as e:
        return JSONResponse(content={"message": f"Error loading model: {str(e)}"}, status_code=500)

    lora_chat_template_dict[lora.url] = error_maybe_template
    return JSONResponse(content={"message": "Model loaded successfully" if is_lora_loaded else "Could not be loaded"},
                        status_code=200)


@router.post("/lora/unload")
async def unload_model(lora_url: str = Form(...),
                       current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    global lora_chat_template_dict

    lora = await get_user_lora_by_url(current_user, db, lora_url)
    if not lora:
        return JSONResponse(content={"message": "Model not found"}, status_code=404)

    lora_int_id = await hash_lora_str_id(lora.url)
    await set_last_model_lora(db, current_user, lora_id='')

    try:
        from app.core.engine import openai_serving_chat
        lora_list = {lora.lora_int_id for lora in openai_serving_chat.lora_requests}
        if lora_int_id not in lora_list:
            return JSONResponse(content={"message": "Model not loaded"}, status_code=404)
        is_lora_unloaded = openai_serving_chat.engine_client.engine.remove_lora(lora_int_id)
        if not is_lora_unloaded:
            return JSONResponse(content={"message": "Could not be unloaded"}, status_code=404)
        openai_serving_chat.lora_requests = [lora for lora in openai_serving_chat.lora_requests if
                                             lora.lora_int_id != lora_int_id]
    except Exception as e:
        return JSONResponse(content={"message": f"Error unloading model: {str(e)}"}, status_code=500)

    lora_chat_template_dict.pop(lora.url, None)
    return JSONResponse(
        content={"message": "Model unloaded successfully" if is_lora_unloaded else "Could not be unloaded"},
        status_code=200)


@router.post("/lora/push_online")
async def push_lora_online(
        lora_name: str = Form(...),
        lora_local_id: str = Form(...),
        lora_description: str = Form(None),
        lora_url: str = Form(...),
        id_model: str = Form(...),
        lora_tags: str = Form(None),
        image: Union[UploadFile, str] = Form(None),
        is_private: bool = Form(False),
        is_new_item: bool = Form(False),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)):
    if not is_new_item:
        await edit_lora_async(db, lora_id=lora_local_id, name=lora_name, description=lora_description, image=image,
                              is_private=is_private)
    else:
        try:
            response = await create_lora_async(db, lora_name, lora_description, image, id_model, lora_url, is_private,
                                               tags=lora_tags)
            await change_lora_id_and_owner(db, lora_local_id, response['id'], response['owner'], current_user)
        except Exception as e:
            raise HTTPException(detail=f"Error pushing lora online: {str(e)}", status_code=500)
    return JSONResponse(content={"message": "LoRA pushed successfully"})
