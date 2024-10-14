import hashlib
import json
import os
from typing import Union, Optional, List

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.db.db_common import get_entity, ask_pulsar_for_id
from app.db.ml_models.model_db import get_model
from app.utils.models.model_paths import get_hf_path
from app.db.model.auth import User
from app.db.model.lora import LoRA
from app.utils.log import setup_custom_logger
from app.utils.models.list_model import list_loras_hf
from app.utils.models.tokenizer_template_inferrer import maybe_get_chat_template
from app.utils.server.api_calls_to_main import make_api_request

logger = setup_custom_logger(__name__)

async def get_lora_list(current_user: User, db: AsyncSession, model_arch: str = None) -> Union[LoRA, None, List[LoRA]]:
    """
    Get a list of LoRA entities associated with the current user.

    Args:
        current_user (User): The user requesting the LoRA list.
        db (AsyncSession): The database session.
        model_arch (str, optional): The model architecture to filter by.

    Returns:
        Union[LoRA, None, List[LoRA]]: A list of LoRA entities or None.
    """
    return await get_entity(db, LoRA, user_id=current_user.id, model_architecture=model_arch)

async def establish_if_lora(lora_url: str, db: AsyncSession) -> bool:
    """
    Check if a LoRA entity exists in the database by name.

    Args:
        lora_url (str): The url of the LoRA entity.
        db (AsyncSession): The database session.

    Returns:
        bool: True if the LoRA entity exists, False otherwise.
    """
    loras = await get_entity(db, LoRA, url=lora_url, return_all=True)
    return len(loras) > 0

async def get_lora(db: AsyncSession, lora_url: str = None, lora_name: str = None):
    """
    Retrieve a LoRA entity by URL or name.

    Args:
        db (AsyncSession): The database session.
        lora_url (str, optional): The URL of the LoRA entity.
        lora_name (str, optional): The name of the LoRA entity.

    Returns:
        LoRA: The retrieved LoRA entity.
    """
    return await get_entity(db, LoRA, url=lora_url if not lora_name else None, name=lora_name)

async def get_lora_id_from_online(db, name, description, image, model_id, url, is_private) -> str:
    """
    Get or create a LoRA ID based on online status.

    Args:
        db (AsyncSession): The database session.
        name (str): The name of the LoRA.
        description (str): The description of the LoRA.
        image (UploadFile): The image of the LoRA.
        model_id (str): The model ID associated with the LoRA.
        url (str): The URL of the LoRA.
        is_private (bool): Whether the LoRA is private.

    Returns:
        str: The LoRA ID.
    """
    lora_id = await ask_pulsar_for_id(db, url, 'lora')
    if not lora_id:
        response = await create_lora_async(db, name, description, image, model_id, url, is_private)
        lora_id = response['id']
    return lora_id

async def edit_lora_async(db: AsyncSession, name: str, description: str, image: UploadFile, is_private: bool, lora_id: str, tags: str=None):
    """
    Edit a LoRA entity asynchronously.

    Args:
        db (AsyncSession): The database session.
        name (str): The new name of the LoRA.
        description (str): The new description of the LoRA.
        image (UploadFile): The new image of the LoRA.
        is_private (bool): Whether the LoRA is private.
        lora_id (str): The ID of the LoRA to be edited.
        tags (str, optional): Tags associated with the LoRA.

    Returns:
        dict: The response from the API call.
    """
    files = {}
    if image:
        files["lora_image"] = image.file
    param_dict = {
        "lora_id": lora_id,
        "lora_name": name,
        "lora_description": description,
        "lora_is_private": is_private,
    }
    if tags:
        param_dict.update({'lora_tags': tags})
    response = await make_api_request(db, "PUT", "/lora/edit", param_dict, files)
    return response

async def create_lora_async(db: AsyncSession, name: str, description: str, image: UploadFile, model_id: str, url: str, is_private: bool, tags: str=None):
    """
    Create a LoRA entity asynchronously.

    Args:
        db (AsyncSession): The database session.
        name (str): The name of the LoRA.
        description (str): The description of the LoRA.
        image (UploadFile): The image of the LoRA.
        model_id (str): The model ID associated with the LoRA.
        url (str): The URL of the LoRA.
        is_private (bool): Whether the LoRA is private.
        tags (str, optional): Tags associated with the LoRA.

    Returns:
        dict: The response from the API call.
    """
    form_data = {
        "model_id": model_id,
        "lora_private_token": os.environ.get("PULSAR_HF_TOKEN", None) if os.environ.get("PULSAR_SHOULD_SEND_PRIVATE_TOKEN", False) else None,
        "lora_name": name,
        "lora_description": description,
        "lora_url": url,
        "lora_tags": tags,
        "lora_is_private": str(is_private),
    }

    files = {}
    if image:
        files["lora_image"] = image.file
    return await make_api_request(db, "POST", "/lora/create", form_data, files)

async def delete_lora_async(db: AsyncSession, lora_id):
    """
    Delete a LoRA entity asynchronously.

    Args:
        db (AsyncSession): The database session.
        lora_id (str): The ID of the LoRA to be deleted.

    Returns:
        int: Status code indicating success (200).
    """
    await make_api_request(db, "DELETE", "/lora/delete", {"id": lora_id})
    return 200

async def get_user_lora(current_user: User, db: AsyncSession, lora_id: str = None, lora_name: str = None):
    """
    Get a LoRA entity associated with the current user.

    Args:
        current_user (User): The current user.
        db (AsyncSession): The database session.
        lora_id (str, optional): The ID of the LoRA.
        lora_name (str, optional): The name of the LoRA.

    Returns:
        LoRA: The retrieved LoRA entity.
    """
    return await get_entity(db, LoRA, user_id=current_user.id, id=lora_id, name=lora_name)

async def change_lora_id_and_owner(db: AsyncSession, model_local_id: str, lora_id: str, owner: str, current_user: User):
    """
    Change the LoRA ID and owner.

    Args:
        db (AsyncSession): The database session.
        model_local_id (str): The local ID of the model.
        lora_id (str): The new LoRA ID.
        owner (str): The new owner of the LoRA.
        current_user (User): The current user.

    Raises:
        Exception: If the LoRA entity is not found.
    """
    lora = await get_entity(db, LoRA, id=model_local_id, user_id=current_user.id)
    if not lora:
        raise Exception("LoRA not found")
    lora.id = lora_id
    lora.owner = owner
    db.add(lora)
    await db.commit()

async def get_user_lora_by_url(current_user: User, db: AsyncSession, url: str = None):
    """
    Get a LoRA entity by URL for the current user.

    Args:
        current_user (User): The current user.
        db (AsyncSession): The database session.
        url (str, optional): The URL of the LoRA.

    Returns:
        LoRA: The retrieved LoRA entity.
    """
    return await get_entity(db, LoRA, user_id=current_user.id, url=url)

async def hash_lora_str_id(text: str) -> Optional[int]:
    """
    Hash a string to an integer, needed for the LoRA id in vllm.

    This method uses the first 8 hex digits of the SHA-1 hash to generate the integer.

    Args:
        text (str): The input string to hash.

    Returns:
        Optional[int]: An integer representation of the truncated hash, or None if the text is empty.
    """
    if not text:
        return
    hash_object = hashlib.sha1(text.encode())
    hex_dig = hash_object.hexdigest()
    return int(hex_dig[:8], 16)

async def is_lora_correct(lora: LoRA, db: AsyncSession):
    """
    Check if a LoRA entity is correct and compatible with a given model.

    Args:
        lora (LoRA): The LoRA entity to check.
        db (AsyncSession): The database session.

    Returns:
        tuple: A boolean indicating compatibility and a message or template.
    """
    from app.core.engine import openai_serving_chat
    model_url = (await openai_serving_chat.engine_client.get_model_config()).model
    model = await get_model(db, model_url)
    if not model:
        error = "Could not determine if the lora and the model architecture are compatible, this could lead to errors."
        logger.error(error)
        return False, error

    query = select(LoRA).where(and_(LoRA.name == lora.name, LoRA.base_architecture == model.base_architecture))
    loras = (await db.execute(query)).scalars().all()
    if len(loras) > 0:
        chat_template = await maybe_get_chat_template(lora.url)
        if not chat_template:
            error = "Could not retrieve the chat template, this lora is unusable since transformer 0.44 unless you manually specify a chat template."
            logger.error(error)
            return False, error

        return True, chat_template
    return False, "LoRA is not compatible with this model, please load a model with a correct architecture first."

async def get_orignal_model_name(lora_name):
    """
    Get the original model name associated with a LoRA.

    Args:
        lora_name (str): The name of the LoRA.

    Returns:
        str: The base model name or path.
    """
    model_dir = await list_loras_hf(await get_hf_path(lora_name))
    with open(os.path.join(model_dir, 'adapter_config.json')) as f:
        lora_conf = json.load(f)
    return lora_conf.get("base_model_name_or_path", None)