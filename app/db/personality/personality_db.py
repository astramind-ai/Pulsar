import json
from typing import List, Union
from typing import Optional

from fastapi import UploadFile
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.model.personality import Personality
from app.utils.formatting.pydantic.personality import PersonalitySchema
from app.utils.server.api_calls_to_main import make_api_request


async def set_personality_model_request_as_dict(personality_name: str, personality_description: str) -> List[dict]:
    return [{'content': 'Carefully answer the user request, be concise, precise and thoughtful.', 'role': 'system'},
            {
                'content': f'Based on this description: [Name: {personality_name}, Charachter Description:{personality_description}] answer the following question: ',
                'role': 'user'}]


async def get_personality(db: AsyncSession, name: str, user: str):
    result = await db.execute(select(Personality).where(and_(Personality.name == name, Personality.users.any(id=user))))
    return result.scalars().first()


async def get_personality_by_id(db: AsyncSession, name: str, user: str = None):
    conditions = [Personality.id == name]
    if user:
        conditions.append(or_(Personality.owner == 'everyone', Personality.users.any(id=user)))

    result = await db.execute(
        select(Personality)
        .options(joinedload(Personality.users))
        .where(and_(*conditions)
               )
    )
    return result.scalars().first()


async def get_user_personality_list(db: AsyncSession, user_id: str):
    result = await db.execute(select(Personality).where(Personality.users.any(id=user_id), ))
    return result.scalars().all()


def format_dict_to_string(input_dict: Union[str, dict]):
    """
    Converts a string into a dictionary and then into a string format where each key-value pair is
    represented as 'key = value' on a new line.

    Parameters:
    - input_dict (dict): The dictionary to format.

    Returns:
    - str: A string representation of the dictionary with each item on a new line.
    """
    if isinstance(input_dict, str):
        input_dict = json.loads(input_dict)
    formatted_items = [f"{key} = {value}" for key, value in input_dict.items()]
    # Join all the items with a newline personality
    result_string = "\n".join(formatted_items)
    return result_string


async def download_personality_from_server(db: AsyncSession, personality_id: str):
    response = await make_api_request(db, "GET", f"/personality/list?personality_id={personality_id}")
    return response['personality']


async def edit_personality_async(
        db: AsyncSession,
        # describe_scene: bool,
        personality_id: str,
        name: str,
        description: str,
        pre_prompt: str,
        image: Optional[UploadFile],
        is_private: bool
):

    data = {
        "personality_id": personality_id,
        "personality_name": name,
        "personality_description": description,
        "personality_preprompt": pre_prompt,
        # "personality_describe_scene": str(describe_scene),
        "personality_is_private": str(is_private),
    }

    files = {}

    if image:
        files["personality_image"] = image.file
    return await make_api_request(db, "PUT", "/personality/edit", data, files)


async def delete_personality_async(db: AsyncSession, personality_id):
    await make_api_request(db, "DELETE", "/personality/delete", {"id": personality_id})
    return 200


async def create_personality_async(
        db: AsyncSession,
        tags: str,
        # describe_scene: bool,
        name: str,
        description: str,
        pre_prompt: dict,
        image: Optional[UploadFile],
        is_private: bool
):
    if isinstance(pre_prompt, dict):
        pre_prompt = json.dumps(pre_prompt)  # Ensure pre_prompt is JSON serialized

    data = {
        "personality_name": name,
        "personality_description": description,
        "personality_preprompt": pre_prompt,
        "personality_tags": tags,
        # "personality_describe_scene": str(describe_scene),
        "personality_is_private": str(is_private),
    }

    files = {}

    if image:
        files["personality_image"] = image.file

    return await make_api_request(db, "POST", "/personality/create", data, files)


async def change_personality_id_and_owner(db, model_local_id, personality_id, owner, current_user_username):
    query = select(Personality).where(
        and_(or_(Personality.users.any(username=current_user_username), Personality.owner == 'everyone'),
        Personality.id == model_local_id)
    )
    result = await db.execute(query)
    personality = result.scalars().first()
    if not personality:
        raise Exception("Personality not found")
    personality.id = personality_id
    personality.owner = owner
    db.add(personality)
    await db.commit()


# Function to modify specific fields in the personality JSON
def modify_personality_fields(personality: PersonalitySchema, updates: dict):
    for field, value in updates.items():
        if hasattr(personality, field):
            setattr(personality, field, value)
    return personality
