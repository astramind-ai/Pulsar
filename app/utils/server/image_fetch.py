import os

from fastapi import HTTPException
from starlette.responses import FileResponse

from app.utils.formatting.pydantic.request import ImageRequest
from app.utils.definitions import UPLOAD_DIRECTORY


async def get_image(image_request: ImageRequest):
    """
    Get the image from the specified URL
    """

    image_path = os.path.abspath(f"{UPLOAD_DIRECTORY}/{image_request.image_name}")

    # Verify that the image exists
    if not os.path.exists(image_path) or not os.path.isfile(image_path):
        raise HTTPException(status_code=404, detail="Image not found")

    # return the image
    return FileResponse(image_path)