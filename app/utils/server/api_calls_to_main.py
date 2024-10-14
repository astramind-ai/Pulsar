import asyncio
from typing import Optional, Dict, Any

import httpx
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.definitions import SERVER_URL

refresh_lock = asyncio.Lock()

async def make_api_request(
        db: AsyncSession,
        method: str,
        endpoint: str,
        param_dict: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
        json_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from app.db.tokens.db_token import get_access_token, get_refresh_token, set_access_token, set_refresh_token


    async def get_tokens() -> Dict[str, str]:
        return {
            "access_token": await get_access_token(db),
            "refresh_token": await get_refresh_token(db)
        }

    async def set_tokens(access_token: str, refresh_token: str):
        await set_access_token(access_token, db)
        await set_refresh_token(refresh_token, db)

    async def refresh_token() -> bool:
        tokens = await get_tokens()
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{SERVER_URL}/refresh",
                headers={"refresh-token": tokens["refresh_token"]}
            )
        if response.status_code == 200:
            new_tokens = response.json()
            await set_tokens(new_tokens["access_token"], new_tokens["refresh_token"])
            return True
        return False

    async def send_request() -> httpx.Response:
        tokens = await get_tokens()
        if headers is None:
            headers_ = {
                "Authorization": f"Bearer {tokens['access_token']}",
                "refresh-token": tokens["refresh_token"]
            }
        else:
            headers_ = headers

        url = f"{SERVER_URL}{endpoint}"
        async with httpx.AsyncClient(timeout=60) as client:
            return await client.request(method, url, headers=headers_, data=param_dict, json=json_dict, files=files)

    response = await send_request()
    if response.status_code == 401:
        async with refresh_lock:
            await refresh_token()
        response = await send_request()

    if response.status_code >= 400:
        try:
            message = response.json().get('message', response.text)
            if "already exist" in message:
                message += ". You can upload it privately or edit the existing name"
            raise HTTPException(status_code=response.status_code, detail=message)
        except Exception as e:
            response.raise_for_status()

    return response.json()
