import base64
import json
import os
import time

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.model.token import Token
from app.utils.database.get import get_db
from app.utils.server.api_calls_to_main import make_api_request


async def get_access_token(db: AsyncSession):
    token = await db.execute(select(Token).filter(Token.id == 1))
    token = token.scalars().first()
    if token is None:
        return None
    return token.access_token


async def get_refresh_token(db: AsyncSession):
    token = await db.execute(select(Token).filter(Token.id == 1))
    token = token.scalars().first()
    if token is None:
        return None
    return token.refresh_token


async def set_access_token(access_token: str, db: AsyncSession):
    token = await db.execute(select(Token).filter(Token.id == 1))
    token = token.scalars().first()
    token.access_token = access_token
    await db.commit()


async def set_refresh_token(refresh_token: str, db: AsyncSession):
    token = await db.execute(select(Token).filter(Token.id == 1))
    token = token.scalars().first()
    token.refresh_token = refresh_token
    await db.commit()


async def get_setter_token(expiration_time=3600):
    private_key = serialization.load_pem_private_key(os.environ.get('PULSAR_PRIVATE_KEY').replace("\\n", "\n").encode(), password=None)

    payload = {
        'user_id': os.environ.get('PULSAR_USER_ID'),
        'exp': int(time.time()) + expiration_time
    }

    payload_bytes = json.dumps(payload).encode()
    signature = private_key.sign(
        payload_bytes,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )

    token = base64.urlsafe_b64encode(payload_bytes + signature).decode()
    return token


async def set_url_token(url_token: str, db: AsyncSession = Depends(get_db)):
    token = await db.execute(select(Token).filter(Token.id == 1))
    token = token.scalars().first()
    token.url_token = url_token
    await db.commit()


async def set_local_url_online(url: str):
    async for db in get_db():
        setter_token = await get_setter_token()

        headers = {
            "token": f"{setter_token}",
            "user-id": f"{os.environ.get('PULSAR_USER_ID')}"
        }

        await make_api_request(db, "PUT", "/update_url", json_dict={"url": url}, headers=headers)

    return 200  # if the request is successful
