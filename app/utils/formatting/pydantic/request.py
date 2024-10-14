import re
from pathlib import Path

from pydantic import BaseModel, field_validator, Field, ConfigDict

from app.utils.definitions import ALLOWED_EXTENSIONS, ABSOLUTE_UPLOAD_DIRECTORY, UPLOAD_DIRECTORY


class ImageRequest(BaseModel):
    image_name: str = Field(..., alias="image_name")

    @field_validator('image_name')
    def sanitize_image_name(cls, v: str, values: dict) -> str:
        if not re.match(r'^[a-zA-Z0-9_\-./ ]+$', v):
            raise ValueError("Image name contains invalid characters")

        # Previeni l'attraversamento delle directory
        safe_path = (Path(UPLOAD_DIRECTORY) / v).resolve()
        if not safe_path.is_relative_to(ABSOLUTE_UPLOAD_DIRECTORY):
            raise ValueError("Invalid file path")

        file_extension = v.split('.')[-1].lower()
        if file_extension not in ALLOWED_EXTENSIONS:
            raise ValueError(f"File Extension not permitted. Permitted ones are: {', '.join(ALLOWED_EXTENSIONS)}")

        return str(safe_path.relative_to(ABSOLUTE_UPLOAD_DIRECTORY))

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=None
    )


class EnvVar(BaseModel):
    key: str
    value: str
    reboot_required: bool = False