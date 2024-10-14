import os
import warnings
from typing import Union

from fastapi import APIRouter, Depends, UploadFile, Form, HTTPException
from httpx import HTTPStatusError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from app.db.auth.auth_db import get_current_user
from app.db.model.auth import User
from app.db.model.persona import Persona
from app.db.persona.persona_db import get_persona, create_persona_async, \
    get_user_persona_list, get_persona_by_name, change_persona_id_and_owner, delete_persona_async, edit_persona_async
from app.utils.database.get import get_db
from app.utils.database.images import save_image, delete_image
from app.utils.formatting.pydantic.privacy import PrivacyOptions
from app.utils.formatting.pydantic.request import ImageRequest
from app.utils.server.image_fetch import get_image
from app.utils.definitions import UPLOAD_DIRECTORY

warnings.filterwarnings("ignore", category=UserWarning, message=".*has conflict with protected namespace *")

router = APIRouter()


@router.get("/persona_image/{image_name}")
async def get_router_image(image_name: str):
    image_request = ImageRequest(image_name=image_name)
    return await get_image(image_request)


@router.post("/persona/create")
async def add_persona(persona_name: str = Form(...),
                      persona_description: str = Form(...),
                      persona_image: Union[UploadFile, str] = Form(...),
                      personality_id: str = Form(...),
                      lora_id: str = Form(None),
                      model_id: str = Form(...),
                      privacy_settings: PrivacyOptions = Form(...),
                      current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    persona = await get_persona_by_name(db, persona_name, current_user.id)
    if persona:
        raise HTTPException(status_code=400, detail="persona name already choosen")

    new_filename = save_image(current_user, persona_image)

    if privacy_settings != "local":
        try:
            await create_persona_async(db, name=persona_name, description=persona_description,
                                       image=persona_image,
                                       personality_id=personality_id,
                                       lora_id=lora_id, model_id=model_id,
                                       is_private=privacy_settings == "private")
        except Exception as e:
            if isinstance(e, HTTPException):
                if "does not exist" in e.detail:
                    e.detail += ". Please be sure you have synced the model/lora/personality with the online server"
                raise e
            elif isinstance(e, HTTPStatusError):
                if "does not exist" in e.response.json().get("message", ""):
                    e.response.json()["message"] += ". Please be sure you have synced the model/lora/personality with the online server"
            raise HTTPException(status_code=500, detail="Online persona creation failed, " + str(e))

    # use the id returned form the call
    persona = Persona(name=persona_name, description=persona_description,
                      image=await new_filename,
                      personality_id=personality_id,
                      lora_id=lora_id, model_id=model_id,
                      users=[current_user], owner=current_user.name
                      )
    db.add(persona)
    await db.commit()
    await db.refresh(persona)
    return {"status": "persona created successfully"}


@router.put("/persona/edit")
async def update_persona(
        persona_id: str = Form(...),
        persona_name: str = Form(None),
        persona_description: str = Form(None),
        persona_image: Union[UploadFile, str] = Form(None),
        lora_id: str = Form(None),
        model_id: str = Form(None),
        personality_id: str = Form(None),
        privacy_settings: PrivacyOptions = Form(None),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)):
    persona = await get_persona(db, persona_id, current_user.id)

    if not persona:
        raise HTTPException(status_code=404, detail="persona not found")
    if persona_name:
        persona.name = persona_name
    if persona_description:
        persona.description = persona_description
    if persona_image:
        new_filename = await save_image(current_user, persona_image)
        await delete_image(persona)
        persona.image = new_filename
    if lora_id:
        persona.lora_id = lora_id
    if model_id:
        persona.model_id = model_id
    if personality_id:
        persona.personality_id = personality_id

    db.add(persona)
    await db.commit()
    if privacy_settings and privacy_settings.value != "local":
        try:
            await edit_persona_async(db, name=persona_name, description=persona_description, image=persona_image,
                                     is_private=True if privacy_settings.value == "private" else False, persona_id=persona.id,
                                     model_id=model_id, lora_id=lora_id, personality_id=personality_id)
        except Exception as e:
            raise HTTPException(detail=f"Error pushing edited model online: {str(e)}",
                                status_code=500)
    return {"message": "persona updated successfully"}


@router.post("/persona/download")
async def download_persona(
        persona_id: str = Form(...),
        persona_name: str = Form(...),
        persona_description: str = Form(...),
        persona_model_id: str = Form(...),
        persona_personality_id: str = Form(...),
        persona_lora_id: str = Form(None),
        persona_image: Union[UploadFile, str] = Form(None),
        persona_is_private: bool = Form(False),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    persona = await get_persona(db, persona_id)
    if persona:
        if any([current_user.id not in user.id for user in persona.users]):
            persona.users.append(current_user)
            await db.commit()
            return JSONResponse(content={"message": "Persona downloaded successfully"})
        else:
            raise HTTPException(status_code=409, detail="Persona already downloaded")
    image_filename = None
    if persona_image:
        image_filename = await save_image(current_user, persona_image)

    persona = Persona(
        id=persona_id,
        user_username=current_user.name,
        name=persona_name,
        owner=current_user.name,
        description=persona_description,
        personality_id=persona_personality_id,
        lora_id=persona_lora_id,
        model_id=persona_model_id,
        image=image_filename,
        users=[current_user],
    )
    db.add(persona)
    await db.commit()
    return JSONResponse(content={"message": "Persona downloaded successfully"})


@router.delete("/persona/delete")
async def delete_persona(persona_id: str = Form(...),
                         also_delete_online: bool = Form(False),
                         current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    if also_delete_online:
        await delete_persona_async(db, persona_id)

    persona = await get_persona(db, persona_id, current_user.id)
    if not persona and not also_delete_online:
        raise HTTPException(status_code=404, detail="persona not found")
    elif not persona:
        return {"message": "persona deleted successfully"}
    await delete_image(persona)
    await db.delete(persona)
    await db.commit()
    return {"message": "persona deleted successfully"}


@router.get("/persona/list")
async def list_persona(current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    persona_list = await get_user_persona_list(db, current_user.id)
    persona_final_list = []
    for persona in persona_list:
        personalities = {}
        for var in vars(persona):
            if var != "users" and var != "lora" and var != "model" and var != "personality":
                personalities[var] = getattr(persona, var)
            personalities[var] = getattr(persona, var)
        persona_final_list.append(personalities)

    return {"persona": persona_final_list}


@router.post("/persona/push_online")
async def push_lora_online(
        persona_name: str = Form(...),
        persona_local_id: str = Form(...),
        persona_description: str = Form(None),
        id_model: str = Form(...),
        id_personality: str = Form(...),
        id_lora: str = Form(None),
        image: Union[UploadFile, str] = Form(None),
        is_private: bool = Form(False),
        is_new_item: bool = Form(False),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)):
    if not is_new_item:
        await edit_persona_async(db, persona_local_id, persona_name, persona_description, id_model, id_lora,
                                 id_personality, image, is_private)
    else:
        response = await create_persona_async(db, is_private, id_personality, persona_name, persona_description, image,
                                              id_lora, id_model)
        try:
            await change_persona_id_and_owner(db, persona_local_id, response['id'], response['owner'], current_user)
        except Exception as e:
            raise HTTPException(detail=f"Error pushing persona online: {str(e)}", status_code=500)
    return JSONResponse(content={"message": "Persona pushed online successfully"})
