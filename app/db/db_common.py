from functools import wraps
from typing import List, Optional, Union, Type, Any

import cachetools
from fastapi.security import OAuth2PasswordBearer

from sqlalchemy import select, or_, and_, Sequence, ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, UploadFile, Depends

from app.db.model.auth import User
from app.db.model.ml_model import Model
from app.db.model.lora import LoRA
from app.db.model.personality import Personality
from app.db.model.chat import Chat, Message
from app.utils.definitions import ACCESS_TOKEN_EXPIRE_MINUTES
from app.utils.server.api_calls_to_main import make_api_request
from app.utils.database.images import save_image

EntityType = Union[User, Model, LoRA, Personality, Chat, Message]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_entity(db: AsyncSession, entity_class: Type[EntityType], id: str = None,
                     user_id: Optional[str] = None, url: str =None, name: str=None,
                     model_architecture:str =None, return_all: bool = False,
                     added_conditions: Union[ColumnElement[bool], bool] =None) -> Optional[Union[Sequence[EntityType], EntityType]]:
    conditions = []
    if url:
        conditions.append(entity_class.url == url)
    if name:
        conditions.append(entity_class.name == name)
    if model_architecture:
        conditions.append(entity_class.base_architecture == model_architecture)
    if id:
        conditions.append(entity_class.id == id)
    if user_id and hasattr(entity_class, 'users'):
        conditions.append(or_(entity_class.users.any(id=user_id), entity_class.owner == 'everyone'))
    if added_conditions:
        conditions.append(added_conditions)


    # if either name, url or id is provoded we get one otherwise we get a list
    query = select(entity_class).where(and_(*conditions))
    result = await db.execute(query)

    if (not name and not url and not id) or return_all:
        return result.scalars().all()
    return result.scalars().first()

async def ask_pulsar_for_id(db:AsyncSession, url: str, entity_type: str) -> Optional[str]:
    try:
        response = await make_api_request(db, "GET", f"/{entity_type}/get_id_from_url", {f"{entity_type}_url": url})
    except HTTPException as e:
        return None
    return response["id"]


async def create_entity_async(db: AsyncSession, entity_type: str, data: dict,
                              image: Optional[UploadFile] = None) -> dict:
    files = {}
    if image:
        files[f"{entity_type}_image"] = image.file
    return await make_api_request(db, "POST", f"/{entity_type}/create", data, files)


async def edit_entity_async(db: AsyncSession, entity_type: str, entity_id: str, data: dict,
                            image: Optional[UploadFile] = None) -> dict:
    files = {}
    if image:
        files[f"{entity_type}_image"] = image.file
    data[f"{entity_type}_id"] = entity_id
    return await make_api_request(db, "PUT", f"/{entity_type}/edit", data, files)


async def delete_entity_async(db: AsyncSession, entity_type: str, entity_id: str) -> int:
    await make_api_request(db, "DELETE", f"/{entity_type}/delete", {"id": entity_id})
    return 200


async def change_entity_id_and_owner(db: AsyncSession, entity_class: Type[EntityType], local_id: str, new_id: str,
                                     new_owner: str, current_user_username: str):
    query = select(entity_class).where(
        and_(or_(entity_class.users.any(username=current_user_username), entity_class.owner == 'everyone'),
             entity_class.id == local_id)
    )
    result = await db.execute(query)
    entity = result.scalars().first()
    if not entity:
        raise HTTPException(status_code=404, detail=f"{entity_class.__name__} not found")
    entity.id = new_id
    entity.owner = new_owner
    db.add(entity)
    await db.commit()


async def add_entity_to_db(db: AsyncSession, entity_class: Type[EntityType], data: dict, current_user: User,
                           image: Optional[UploadFile] = None) -> EntityType:
    image_filename = await save_image(current_user, image) if image else None
    entity = entity_class(**data, image=image_filename, users=[current_user])
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    return entity


# Specific functions that don't fit into the generic pattern
async def get_chat_history(db: AsyncSession, chat_id: str, up_to_message_id: Optional[str] = None) -> List[Message]:
    query = select(Message).where(Message.chat_id == chat_id)
    if up_to_message_id:
        subquery = select(Message.timestamp).where(and_(
            Message.chat_id == chat_id,
            Message.id == up_to_message_id
        )).scalar_subquery()
        query = query.where(Message.timestamp <= subquery)
    query = query.order_by(Message.timestamp)
    result = await db.execute(query)
    return result.scalars().all()


async def get_current_model(db: AsyncSession) -> Model:
    from app.core.engine import async_engine
    model_name = await async_engine.get_model_config()
    result = await db.execute(select(Model).filter(Model.url == model_name.model))
    return result.scalars().first()

# Add more specific functions as needed