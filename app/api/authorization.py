import os
import shutil
import uuid

from fastapi import Depends, HTTPException, status, APIRouter, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

# Database and utility imports for user authentication and file handling.
from app.db.auth.auth_db import authenticate_user, create_access_token, get_current_user, get_user, create_user, \
    get_current_user_for_login
from app.db.model.auth import User
from app.utils.database.get import get_db
from app.utils.definitions import UPLOAD_DIRECTORY
from app.utils.formatting.pydantic.request import ImageRequest
from app.utils.formatting.pydantic.token import AuthToken
from app.utils.server.image_fetch import get_image

router = APIRouter()

# Endpoint to retrieve user images by name.
@router.get("/user_image/{image_name}")
async def get_router_image(image_name: str):
    image_request = ImageRequest(image_name=image_name)
    return await get_image(image_request)

# Endpoint for login and token generation.
@router.post("/token", response_model=AuthToken)
async def login_for_access_token(username: str = Form(...), validate_token=Depends(get_current_user_for_login), db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    access_token = create_access_token(data={"sub": user.name})
    return JSONResponse({"access_token": access_token, "token_type": "bearer"})

# Endpoint for updating user details, including username and profile picture.
@router.put("/users/update")
async def update_user(
        username: str = Form(None),
        pfp: UploadFile = File(None),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)):
    user = await get_user(db, current_user.name)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update username if provided
    if username:
        user.name = username
        # Update directory if username changes
        img_path = next((file for file in set(os.listdir(UPLOAD_DIRECTORY)) if current_user.name in file), None)
        if img_path:
            new_img_path = img_path.replace(current_user.name, username)
            if os.path.exists(os.path.join(UPLOAD_DIRECTORY, img_path)):
                shutil.move(os.path.join(UPLOAD_DIRECTORY, img_path), os.path.join(UPLOAD_DIRECTORY, new_img_path))
            user.image = new_img_path

    # Update profile picture if provided
    if pfp:
        uid = uuid.uuid4().hex
        file_location = os.path.join(UPLOAD_DIRECTORY, f"{user.name}_{uid}_{pfp.filename}")
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(pfp.file, buffer)
        user.image = f"{user.name}_{uid}_{pfp.filename}"  # Store just the filename

    db.add(user)
    await db.commit()

    return {"message": "User updated successfully", "new_token": create_access_token(data={"sub": user.name}),
            "username": user.name,
            "profile_picture_url": f"/static/item_images/{user.image if user.image else ''}"}

# Endpoint to delete a user.
@router.delete("/users/delete")
async def delete_user(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user = await get_user(db, current_user.name)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if os.path.exists(os.path.join(UPLOAD_DIRECTORY, user.image)):
        os.remove(os.path.join(UPLOAD_DIRECTORY, user.image))
    await db.delete(user)
    await db.commit()
    return {"message": "User account deleted successfully"}

# Endpoint for user registration.
@router.post("/users/create", response_model=AuthToken)
async def register_user(
        username: str = Form(...),
        pfp: UploadFile = File(...),
        db: AsyncSession = Depends(get_db)
):
    db_user = await get_user(db, username)
    uid = uuid.uuid4().hex
    file_location = os.path.join(UPLOAD_DIRECTORY, f"{username}_{uid}_{pfp.filename}")
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(pfp.file, buffer)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    new_user = await create_user(db, username, f"{username}_{uid}_{pfp.filename}" if pfp else None)
    # Optionally log the user in immediately after registration
    access_token = create_access_token(data={"sub": new_user.name})
    return {"access_token": access_token, "token_type": "bearer"}

# Endpoint to list users, optionally filtered by username.
@router.get("/users/list")
async def list_users(username: str = Form(None), db: AsyncSession = Depends(get_db)):
    if username:
        user = get_user(db, username)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    users = await get_user(db, return_all=True)
    return [{'id': user.id, 'username': user.name, 'pfp': user.image} for user in users]
