import json
import os
import uuid
from json import JSONDecodeError
from sqlite3 import IntegrityError
from typing import Optional, Union

import aiofiles
import aiohttp
from fastapi import APIRouter, Depends, UploadFile, Form, HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import JSONResponse, FileResponse

from app.db.auth.auth_db import get_current_user, get_user
from app.db.db_common import get_entity
from app.db.model.auth import User
from app.db.model.personality import Personality
from app.db.personality.personality_db import set_personality_model_request_as_dict, \
    get_user_personality_list, \
    get_personality, create_personality_async, download_personality_from_server, get_personality_by_id, \
    edit_personality_async, delete_personality_async, change_personality_id_and_owner, modify_personality_fields
from app.utils.formatting.personality.personality_preprompt import create_preprompt
from app.utils.definitions import SERVER_URL
from app.utils.database.get import get_db
from app.utils.database.images import save_image, delete_image
from app.utils.formatting.pydantic.request import ImageRequest
from app.utils.log import setup_custom_logger
from app.utils.formatting.pydantic.privacy import PrivacyOptions
from app.utils.formatting.pydantic.personality import PersonalitySchema
from app.utils.server.image_fetch import get_image
from app.utils.definitions import UPLOAD_DIRECTORY

router = APIRouter()
logger = setup_custom_logger(__name__)


@router.get("/personality_image/{image_name}")
async def get_router_image(image_name: str):
    image_request = ImageRequest(image_name=image_name)
    return await get_image(image_request)


@router.post("/personality/create")
async def add_personality(
        raw_request: Request,
        personality_name: str = Form(...),
        personality_description: str = Form(...),
        personality_image: Union[UploadFile, str] = Form(...),
        # personality_describe_scene: bool = Form(...),
        personality_tags: Optional[str] = Form(None),
        personality_privacy: PrivacyOptions = Form(...),
        auto_generate: bool = Form(...),
        personality_data: Optional[str] = Form(None),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    personality = await get_personality(db, personality_name, current_user.id)
    if personality:
        raise HTTPException(status_code=400, detail="Personality name already choosen")
    image_filename = await save_image(current_user, personality_image)
    online_id, offline_id = None, None
    # Generate personality data
    if auto_generate:
        from app.core.engine import openai_serving_chat
        model_config = (await openai_serving_chat.engine_client.get_model_config())
        model_name = model_config.model
        personality_dict = await set_personality_model_request_as_dict(personality_name, personality_description)

        max_attempts = 5
        attempts = 0
        success = False

        while attempts < max_attempts and not success:
            try:
                preprompt = await create_preprompt(personality_dict, model_name, raw_request, openai_serving_chat)
                personality_description = preprompt.get("description")
                personality_schema = PersonalitySchema(**preprompt).to_dict()
                success = True
            except Exception as e:
                attempts += 1
                if attempts >= max_attempts:
                    logger.error(
                        f"Failed to generate valid personality after {max_attempts} attempts. Last error: {str(e)}")
                    raise HTTPException(status_code=400,
                                        detail=f"Failed to generate valid personality after {max_attempts} attempts. "
                                               f"Last error: {str(e)}")
                else:
                    logger.warn(f"Attempt {attempts} failed. Retrying...")

        if success:
            logger.info(f"Successfully generated personality after {attempts + 1} attempt(s).")
        else:
            raise HTTPException(status_code=500, detail="Unexpected error in personality generation.")
    # Validate user inputted personality data
    else:
        if not personality_data:
            raise HTTPException(status_code=400, detail="Personality data is required for manual creation")
        try:
            personality_data = json.loads(personality_data)
        except JSONDecodeError as e:
            raise HTTPException(status_code=400,
                                detail=f"Invalid personality data formatting, "
                                       f"it should be a json compatible string: {str(e)}")
        try:
            personality_data['name'] = personality_name
            personality_schema = PersonalitySchema.from_form(personality_data).to_dict()
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=f"Invalid personality data: {str(e)}")

    if personality_privacy.value != "local":

        json_response = await create_personality_async(db, tags=personality_tags,
                                                       # describe_scene=personality_describe_scene,
                                                       name=personality_name,
                                                       description=personality_description,
                                                       pre_prompt=personality_schema,
                                                       image=personality_image,
                                                       is_private=personality_privacy.value == "private")

        # use the id returned form the call
        if not json_response.get('id', None):
            raise HTTPException(status_code=500,
                                detail="Personality creation failed, no ID returned from the main server")
        online_id = json_response['id']
        personality = Personality(users=[current_user],
                                  # describe_scene=personality_describe_scene,
                                  name=personality_name,
                                  description=personality_description, pre_prompt=personality_schema,
                                  image=image_filename,
                                  id=online_id, owner=json_response['owner'])
    else:
        offline_id = uuid.uuid4().hex
        personality = Personality(users=[current_user],
                                  # describe_scene=personality_describe_scene,
                                  name=personality_name,
                                  description=personality_description, pre_prompt=personality_schema,
                                  image=image_filename,
                                  id=offline_id, owner=current_user.name)

    db.add(personality)
    await db.commit()
    await db.refresh(personality)
    return {"status": "Personality created successfully", "personality_data": personality_schema, "id": online_id or offline_id}


@router.put("/personality/edit")
async def update_personality(
        personality_id: str = Form(...),
        personality_name: Optional[str] = Form(None),
        personality_description: Optional[str] = Form(None),
        personality_image: Optional[UploadFile] = Form(None),
        privacy_settings: Optional[PrivacyOptions] = Form(None),
        personality_data: Optional[str] = Form(None),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    personality = await get_personality_by_id(db, personality_id, current_user.id)
    if not personality:
        raise HTTPException(status_code=404, detail="Personality not found")

    if personality_name:
        personality.name = personality_name
    if personality_data:
        try:
            personality_data = json.loads(personality_data)
        except JSONDecodeError as e:
            raise HTTPException(status_code=400,
                                detail=f"Invalid personality data formatting, "
                                       f"it should be a json compatible string: {str(e)}")
        previous_schema = personality.pre_prompt
        preprompt = modify_personality_fields(PersonalitySchema.from_form(previous_schema), personality_data).to_dict()
        personality.pre_prompt = json.dumps(preprompt)
    if personality_description:
        personality.description = personality_description
    # if personality_describe_scene:
    # personality.describe_scene = personality_describe_scene
    if personality_image:
        image_filename = await save_image(current_user, personality_image)
        await delete_image(personality)
        personality.image = image_filename
    db.add(personality)
    try:
        await db.commit()
    except IntegrityError:
        raise HTTPException(status_code=400, detail="Personality name already choosen")
    if privacy_settings and privacy_settings.value != "local":
        try:
            await edit_personality_async(db,
                                         # describe_scene=personality_describe_scene,
                                         name=personality_name,
                                         description=personality_description, pre_prompt=personality.pre_prompt,
                                         image=personality_image,
                                         is_private=True if privacy_settings.value == "private" else False,
                                         personality_id=personality.id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)
                                )
    return {"message": "Personality updated successfully"}


@router.delete("/personality/delete")
async def delete_personality(personality_id: str = Form(...),
                             also_delete_online: bool = Form(False),
                             current_user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    if also_delete_online:
        await delete_personality_async(db, personality_id)

    personality = await get_personality_by_id(db, personality_id, current_user.id)
    if not personality and not also_delete_online:
        raise HTTPException(status_code=404, detail="Personality not found")
    elif not personality:
        return {"message": "Personality deleted successfully"}
    await delete_image(personality)
    await db.delete(personality)
    await db.commit()

    return {"message": "Personality deleted successfully"}


@router.get("/personality/list")
async def list_personality(current_user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    personality_list = await get_user_personality_list(db, current_user.id)
    personality_final_list = []
    for personality in personality_list:
        personalities = {}
        for var in vars(personality):
            if var != "users":
                personalities[var] = getattr(personality, var)
        personality_final_list.append(personalities)

    return {"personalities": personality_final_list}


@router.post("/personality/download")
async def download_personality(personality_id: str = Form(...),
                               current_user: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    personality = await get_personality_by_id(db, personality_id)
    if personality:
        if current_user.id not in [user.id for user in personality.users]:
            # add the user to the personality
            user = await get_user(db, current_user.name)
            personality.users.append(user)
            await db.commit()
            return JSONResponse(content={"message": "Personality downloaded successfully"})
        else:
            raise HTTPException(status_code=404, detail="Personality already present")
    else:
        personality_data = await download_personality_from_server(db, personality_id)

        if not personality_data:
            raise HTTPException(status_code=404, detail="Personality not found on the server")

        # Download and save the personality image
        image_url = personality_data['image']

        image_extension = image_url.split('.')[-1]
        image_filename = f"{current_user.name}_{uuid.uuid4().hex}.{image_extension}"
        save_path = os.path.join(UPLOAD_DIRECTORY, image_filename)

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{SERVER_URL}/personality_image/{image_url}") as response:
                if response.status == 200:
                    async with aiofiles.open(save_path, mode='wb') as f:
                        await f.write(await response.read())
                else:
                    raise HTTPException(status_code=500, detail="Failed to download personality image")

        personality = Personality(
            id=personality_id,
            users=[current_user],
            # describe_scene=personality['describe_scene'],
            name=personality_data['name'],
            description=personality_data['description'],
            pre_prompt=personality_data['pre_prompt'],
            image=image_filename,
            owner=personality_data['owner_name'])

        db.add(personality)

        try:
            await db.commit()
        except IntegrityError:
            raise HTTPException(status_code=400, detail="Personality name already choosen")

    return {"message": "Personality downloaded successfully"}


@router.post("/personality/push_online")
async def push_lora_online(
        personality_name: str = Form(...),
        personality_local_id: str = Form(...),
        personality_description: str = Form(...),
        # personality_describe_scene: bool = Form(...),
        tags: Optional[str] = Form(None),
        pre_prompt: str = Form(...),
        image: Union[UploadFile, str] = Form(None),
        is_private: bool = Form(False),
        is_new_item: bool = Form(False),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)):
    if not is_new_item:
        await edit_personality_async(db, personality_local_id, personality_name, personality_description,
                                     pre_prompt, image, is_private)
    else:  # it does not exist
        response = await create_personality_async(db, tags,
                                                  personality_name, personality_description,
                                                  pre_prompt, image, is_private)

        await change_personality_id_and_owner(db, personality_local_id, response['id'], response['owner'], current_user)

    return JSONResponse(content={"message": "Personality pushed online successfully"})
