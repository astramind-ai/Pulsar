from typing import List, Optional

from fastapi import UploadFile
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.model.persona import Persona
from app.utils.server.api_calls_to_main import make_api_request


async def set_persona_model_request_as_dict(persona_name: str, persona_description: str) -> List[dict]:
    return [{'content': 'Generate a detailed persona profile that addresses the following aspects:'
                        ' Appearance, Persona, Motivations, Social Role, and Style Symbolism. '
                        'Ensure each section is concise yet comprehensive.', 'role': 'system'},
            {'content': f'Name: {persona_name}, Charachter Description:{persona_description} ', 'role': 'user'}]


async def change_persona_id_and_owner(db, model_local_id, persona_id, owner, current_user_username):
    query = select(Persona).where(
        and_(or_(Persona.users.any(username=current_user_username), Persona.owner == 'everyone'),
             Persona.id == model_local_id)
    )
    result = await db.execute(query)
    lora = result.scalars().first()
    if not lora:
        raise Exception("Persona not found")
    lora.id = persona_id
    lora.owner = owner
    db.add(lora)
    await db.commit()


async def get_persona(db: AsyncSession, persona_id: str, user_id: str=None):
    if user_id:
        result = await db.execute(select(Persona).where(and_(Persona.id == persona_id, Persona.users.any(id=user_id))))
    else:
        result = await db.execute(select(Persona).where(Persona.id == persona_id))
    return result.scalars().first()


async def get_persona_by_name(db: AsyncSession, name: str, user: str):
    result = await db.execute(select(Persona).where(and_(Persona.name == name, Persona.users.any(id=user))))
    return result.scalars().first()


async def create_persona_async(db, is_private, personality_id, name, description, lora_id, model_id, image):
    data = {"persona_name": name,
            "persona_description": description,
            "persona_lora_id": lora_id,
            "persona_model_id": model_id,
            "persona_personality_id": personality_id,
            "persona_is_private": is_private,
            }
    files = {}
    if image:
        files["persona_image"] = image.file
    return await make_api_request(db, "POST", "/persona/create", data, files)


async def edit_persona_async(
        db: AsyncSession,
        persona_id: str,
        name: str,
        description: str,
        model_id: str,
        lora_id: str,
        personality_id: str,
        image: Optional[UploadFile],
        is_private: bool
):
    data = {
        "persona_id": persona_id,
        "persona_name": name,
        "persona_description": description,
        "persona_model_id": model_id,
        'persona_personality_id': personality_id,
        "persona_lora_id": lora_id,
        # "persona_describe_scene": str(describe_scene),
        "persona_is_private": str(is_private),
    }

    files = {}

    if image:
        files["persona_image"] = image.file

    return await make_api_request(db, "PUT", "/persona/edit", data, files)


async def delete_persona_async(db: AsyncSession, persona_id):
    await make_api_request(db, "DELETE", "/persona/delete", {"id": persona_id})
    return 200


async def get_user_persona_list(db: AsyncSession, user_id: str):
    result = await db.execute(select(Persona).where(or_(Persona.users.any(id=user_id), Persona.owner=='everyone')))
    return result.scalars().all()

