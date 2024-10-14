import asyncio
import os
import uuid
from typing import Optional, List, Union
import ast

from fastapi import UploadFile, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse
from vllm.usage.usage_lib import UsageContext

from app.core.engine import initialize_engine, create_serving_instances
from app.db.auth.auth_db import get_user
from app.db.db_common import get_entity
from app.db.model.auth import User
from app.db.model.ml_model import Model
from app.hijacks.vllm import ExtendedAsyncCompleteServerArgs
from app.middlewares.model_loader_block import set_block_requests
from app.utils.database.images import save_image
from app.utils.log import setup_custom_logger
from app.utils.models.hf_downloader import download_model_async, check_file_in_huggingface_repo
from app.utils.models.list_model import list_models_paths_in_hf_cache, format_repo_name_to_hf
from app.utils.formatting.pydantic.privacy import PrivacyOptions
from app.utils.models.model_paths import get_hf_path
from app.utils.server.api_calls_to_main import make_api_request
from app.utils.server.restarter import restart
from app.utils.definitions import MODEL_PATHS

logger = setup_custom_logger(__name__)


async def get_model_path_or_url(model: Model, variant: str = None) -> str:
    """
    Retrieve the path or URL of a model, optionally based on a variant.

    Args:
        model (Model): The model entity to query.
        variant (str, optional): The specific variant of the model.

    Returns:
        str: The path or URL of the model.

    Raises:
        AssertionError: If the specified variant is not found.
    """
    if variant:
        model_path_dict = ast.literal_eval(model.path).get(variant, None)
        assert model_path_dict, f"Variant {variant} not found in model {model.name}"
        return model_path_dict
    return model.url


async def get_model_list(db: AsyncSession) -> Optional[List[Model]]:
    """
    Get a list of models associated with the current user.

    Args:
        current_user (User): The user whose models to retrieve.
        db (AsyncSession): The database session.

    Returns:
        Optional[List[Model]]: A list of models or None if no models are found.
    """
    return await get_entity(db, Model)


async def get_current_model(db: AsyncSession) -> Optional[Model]:
    """
    Get the currently active model from the engine configuration.

    Args:
        db (AsyncSession): The database session.

    Returns:
        Optional[Model]: The currently active model or None if not found.
    """
    from app.core.engine import async_engine
    model_name = await async_engine.get_model_config()
    return await get_entity(db, Model, url=model_name.model)


async def get_model(db: AsyncSession, url: str = None, model_id: str = None) -> Optional[Model]:
    """
    Retrieve a model based on URL, model ID, or user.

    Args:
        db (AsyncSession): The database session.
        url (str, optional): The URL of the model.
        model_id (str, optional): The unique identifier of the model.
        user (User, optional): The user associated with the model.

    Returns:
        Optional[Model]: The retrieved model or None if not found.
    """
    return await get_entity(db, Model, url=url, id=model_id)


async def change_model_id_and_owner(db: AsyncSession, model_local_id: str, model_id: str, owner: str,
                                    current_user: User):
    """
    Change the model ID and owner for a specified model.

    Args:
        db (AsyncSession): The database session.
        model_local_id (str): The local ID of the model to update.
        model_id (str): The new global ID for the model.
        owner (str): The new owner of the model.
        current_user (User): The current user attempting the operation.

    Raises:
        Exception: If the model is not found in the database.
    """
    model = await get_entity(db, Model, id=model_local_id, user_id=current_user.id)
    if not model:
        raise Exception("Model not found")
    model.id = model_id
    model.owner = owner
    db.add(model)
    await db.commit()


async def download_model_api_(
        model_id: str,
        model_name: str,
        model_arch: str,
        owner: str,
        model_description: str,
        model_url: str,
        file_variant: str,
        tags: str,
        image: Optional[UploadFile],
        current_user: User,
        db: AsyncSession,
        background_tasks: Optional[BackgroundTasks],
        _internal: bool = False,
) -> Optional[Union[JSONResponse, HTTPException]]:
    """
    Handles the API logic for downloading and updating a model, optionally with variant handling.

    Args:
        model_id (str): The global ID for the model.
        model_name (str): The name of the model.
        model_arch (str): The architecture of the model.
        owner (str): The owner of the model.
        model_description (str): The description of the model.
        model_url (str): The URL of the model.
        file_variant (str): The specific file variant to handle.
        tags (str): The tags associated with the model.
        image (UploadFile, optional): The image file associated with the model.
        current_user (User): The current user attempting the operation.
        db (AsyncSession): The database session.
        background_tasks (BackgroundTasks, optional): Background tasks for asynchronous execution.
        _internal (bool, optional): Internal flag to skip certain processing for internal calls.

    Returns:
        Optional[Union[JSONResponse, HTTPException]]: A success message or an HTTP error.
    """
    model_in_db = await get_model(db, model_url)
    image_filename = await save_image(current_user, image)

    if model_in_db:
        if model_in_db.id != model_id and model_in_db.owner == 'everyone':
            model_in_db.id = model_id
            model_in_db.owner = owner
            model_in_db.name = model_name
            model_in_db.base_architecture = model_arch
            model_in_db.variants = file_variant
            model_in_db.image = image_filename
            model_in_db.description = model_description

        if any([current_user.id not in user.id for user in model_in_db.users]):
            db_user = await get_user(db, current_user.name)
            model_in_db.users.append(db_user)
            await db.commit()

        elif file_variant and file_variant not in model_in_db.variants:
            model_in_db.variants = f"{model_in_db.variants},{file_variant}"
            await download_model_async(model_url, file_variant)

            file_variant_path = await list_models_paths_in_hf_cache(
                await format_repo_name_to_hf(model_url),
                file_variant
            )

            old_path_dict = ast.literal_eval(model_in_db.path)
            old_path_dict.update({file_variant: file_variant_path[0]})
            model_in_db.path = str(old_path_dict)

            await db.commit()
        else:
            return JSONResponse(content={"message": "You already have this model"})

        return JSONResponse(content={"message": "Model downloaded successfully"})
    try:
        await download_model_async(model_url, file_variant)

        model = Model(id=model_id, name=model_name, url=model_url, tags=tags,
                      path=str(
                          {file_variant: (await list_models_paths_in_hf_cache(await format_repo_name_to_hf(model_url),
                                                                              file_variant))[0]}) if file_variant else
                      (await list_models_paths_in_hf_cache(await format_repo_name_to_hf(model_url)))[0],
                      working=True, description=model_description, users=[current_user],
                      image=image_filename, variants=file_variant,
                      owner=owner, base_architecture=model_arch)

        db.add(model)
        await db.commit()

        if _internal:
            return
        return JSONResponse(content={"message": "Model downloaded successfully"}, status_code=200)
    except Exception as e:
        raise HTTPException(detail=f"Error downloading model: {str(e)}", status_code=500)


async def get_model_id_from_online(
        db: AsyncSession,
        name: str,
        description: str,
        image: Optional[UploadFile],
        url: str,
        is_private: bool) -> str:
    """
    Retrieves or generates a unique model ID from an online server based on the model URL.

    Args:
        db (AsyncSession): The database session.
        name (str): The name of the model.
        description (str): The description of the model.
        image (UploadFile, optional): The image associated with the model.
        url (str): The URL of the model.
        is_private (bool): Privacy flag indicating if the model is private.

    Returns:
        str: The unique model ID.
    """

    async def ask_server_for_id(
            url: str
    ) -> Optional[str]:
        params = {
            "model_url": url
        }
        try:
            response = await make_api_request(db, "GET", "/model/get_id_from_url", params)
        except HTTPException:
            return None
        return response['id']

    model_id = await ask_server_for_id(url)
    if not model_id:
        response = await create_model_async(db, name, description, image, url, is_private, '')
        model_id = response['id']
    return model_id


async def edit_model_async(
        db: AsyncSession,
        name: str,
        model_tags: str,
        description: str,
        image: UploadFile,
        is_private: bool,
        model_id: str
):
    """
    Edits an existing model's metadata asynchronously.

    Args:
        db (AsyncSession): The database session.
        name (str): The name of the model.
        model_tags (str): Tags associated with the model.
        description (str): The description of the model.
        image (UploadFile): The image file to associate with the model.
        is_private (bool): Flag indicating if the model is private.
        model_id (str): The ID of the model being edited.

    Returns:
        int: HTTP status code indicating success (200).
    """
    files = {}
    if image:
        files["model_image"] = image.file
    data = {
        "id_model": model_id,
        "model_name": name,
        "model_description": description,
        "model_is_private": is_private,
        "model_tags": model_tags,
    }
    await make_api_request(db, "PUT", "/model/edit", data, files)
    return 200


async def generate_entry_for_db(
        model_id: str,
        model_owner: str,
        model_name: str,
        model_description: str,
        model_image: str,
        model_url: str,
        tags: str,
        current_user: User,
        background_tasks
) -> Model:
    """
    Generates a new model entry for the database including server configuration and loading into VRAM.

    Args:
        model_id (str): The model ID.
        model_owner (str): The owner of the model.
        model_name (str): The name of the model.
        model_description (str): The description of the model.
        model_image (str): The image filename for the model.
        model_url (str): The URL of the model.
        tags (str): Tags associated with the model.
        current_user (User): The user associated with the model.
        background_tasks (BackgroundTasks): Background tasks for handling long-running operations.

    Returns:
        Model: The newly created model object.
    """
    from app.core.engine import (openai_serving_chat, delete_engine_model_from_vram, async_engine_args)
    # create a restoration server configuration
    server_conf = ExtendedAsyncCompleteServerArgs.from_yaml("last.yml")
    server_conf.gpu_memory_utilization = async_engine_args.gpu_memory_utilization

    try:
        model = Model(id=model_id, url=model_url, owner=model_owner,
                      name=model_name, image=model_image, tags=tags,
                      path=os.path.join(MODEL_PATHS, await get_hf_path(model_url)),
                      # speed_value=await get_speed(eng_args), working=True,
                      users=[current_user],
                      description=model_description)
    except Exception as e:
        logger.error(f"Error while adding model {model_url} to the database: {e}")
        model = Model(id=model_id, url=model_url, owner=model_owner,
                      name=model_name, tags=tags,
                      path=os.path.join(MODEL_PATHS, await get_hf_path(model_url)),
                      working=False, users=[current_user],
                      description=str(e))
    # try to load the new model, if it fails reload the previous model
    try:
        set_block_requests(True)
        while openai_serving_chat.engine_client.engine.has_unfinished_requests():  # noqa
            await asyncio.sleep(0.1)

        delete_engine_model_from_vram()
        server_conf.model = model_url
        server_conf.tokenizer = model_url
        server_conf.served_model_name = [model_url]
        await initialize_engine(server_conf.get_async_eng_args(), UsageContext.OPENAI_API_SERVER)
        create_serving_instances(server_conf.served_model_name, server_conf)

        server_conf.save_to_yaml()

    except Exception as e:
        background_tasks.add_task(restart(server_conf, True))
        raise HTTPException(status_code=500, detail="Model loading had failed, restarting server, " + str(e))
    finally:
        set_block_requests(False)
    return model


async def add_model_to_db(
        db: AsyncSession,
        model_name: str,
        model_description: str,
        model_image: UploadFile,
        model_image_name: str,
        model_url: str,
        privacy_settings: PrivacyOptions,
        current_user: User,
        tags: str, background_tasks
):
    """
    Adds a new model to the database and handles its download and configuration.

    Args:
        db (AsyncSession): The database session.
        model_name (str): The name of the model.
        model_description (str): The description of the model.
        model_image (UploadFile): The image file for the model.
        model_image_name (str): The name of the image file.
        model_url (str): The URL of the model.
        privacy_settings (PrivacyOptions): The privacy settings for the model.
        current_user (User): The current user associated with the model.
        tags (str): Tags associated with the model.
        background_tasks (BackgroundTasks): Background tasks for asynchronous operations.

    Returns:
        Model: The newly created model object after successful addition to the database.
    """
    base_architecture = await check_file_in_huggingface_repo(model_url, "config.json")
    if not base_architecture:
        raise HTTPException(status_code=404, detail="Model architecture could not be inferred")
    if privacy_settings.value != 'local':

        json_response = await create_model_async(db, name=model_name, tags=tags,
                                                 description=model_description,
                                                 image=model_image,
                                                 is_private=True if privacy_settings.value == "private" else False,
                                                 url=model_url)

        # use the id returned form the call
        if not json_response.get('owner', None):
            raise HTTPException(status_code=500,
                                detail="Personality creation failed, no ID returned from the main server")
        try:
            # download the model
            await download_model_async(model_url)
        except Exception as e:
            raise HTTPException(status_code=500, detail="Model creation failed due to a download issue " + str(e))

        return await generate_entry_for_db(model_id=json_response['id'], model_owner=json_response['owner'],
                                           model_name=model_name, model_description=model_description,
                                           model_image=model_image_name, tags=tags,
                                           model_url=model_url, current_user=current_user,
                                           background_tasks=background_tasks)
    else:
        return await generate_entry_for_db(model_id=str(uuid.uuid4()), model_owner=current_user.name,
                                           model_name=model_name,
                                           model_description=model_description, model_image=model_image_name,
                                           model_url=model_url, tags=tags,
                                           current_user=current_user, background_tasks=background_tasks)


async def create_model_async(
        db: AsyncSession,
        name: str,
        description: str,
        image: UploadFile,
        url: str,
        is_private: bool,
        tags: str
):
    """
    Creates a new model entry asynchronously on the main server and returns the model details.

    Args:
        db (AsyncSession): The database session.
        name (str): The name of the model.
        description (str): The description of the model.
        image (UploadFile): The image associated with the model.
        url (str): The URL of the model.
        is_private (bool): Indicates if the model is private.
        tags (str): Tags associated with the model.

    Returns:
        dict: The response from the server with model details.
    """
    files = {}
    if image:
        files["model_image"] = image.file
    data = {
        "model_name": name,
        "model_description": description,
        "tags": tags,
        "model_token": os.environ.get("PULSAR_HF_TOKEN", None) if os.environ.get("PULSAR_SHOULD_SEND_PRIVATE_TOKEN",
                                                                                 False) else None,
        "model_url": url,
        "model_is_private": is_private,
    }
    return await make_api_request(db, "POST", "/model/create", data, files)


async def delete_model_async(
        db: AsyncSession,
        model_id: str
):
    """
    Deletes a model entry asynchronously from the database.

    Args:
        db (AsyncSession): The database session.
        model_id (str): The ID of the model to be deleted.

    Returns:
        int: HTTP status code indicating success (200).
    """
    await make_api_request(db, "DELETE", "/model/delete", {"id": model_id})
    return 200
