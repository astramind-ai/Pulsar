import io
import os
import shutil
import uuid
from typing import Union

import requests
from PIL import Image
from starlette.datastructures import UploadFile

from app.db.model.auth import User
from app.db.model.lora import LoRA
from app.db.model.ml_model import Model
from app.db.model.persona import Persona
from app.db.model.personality import Personality

from app.utils.definitions import UPLOAD_DIRECTORY, MAX_SIZE


async def save_image(current_user: User, image: Union[UploadFile, str]) -> str:
    # Generate a namefile
    new_filename = f"{current_user.name}_{uuid.uuid4().hex}.{(image.filename if isinstance(image, UploadFile) else image).split('.')[-1]}"
    file_location = os.path.join(UPLOAD_DIRECTORY, new_filename)

    if isinstance(image,str):
        #make the request to the image url sice the one in the frontend was blocked by CORS
        image_data = requests.get(image).content
    else:
        image_data = await image.read()
    img = Image.open(io.BytesIO(image_data))

    # if its too big, resize it
    if img.size[0] > MAX_SIZE[0] or img.size[1] > MAX_SIZE[1]:
        # Ridimensiona l'immagine mantenendo l'aspect ratio
        img.thumbnail(MAX_SIZE)

    img.save(file_location)

    return new_filename


async def delete_image(item: Union[LoRA, Model, Persona, Personality]):
    if item.image and os.path.exists(os.path.join(UPLOAD_DIRECTORY, item.image)):
        os.remove(os.path.join(UPLOAD_DIRECTORY, item.image))
