import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor

import requests
from fastapi import Request, Depends, APIRouter, HTTPException, Form
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse, Response, JSONResponse

from app.db.auth.auth_db import get_current_user, get_online_user_configuration, create_access_token
from app.db.model.auth import User
from app.db.tokens.db_token import get_access_token, set_access_token, set_refresh_token, set_url_token, \
    get_refresh_token, set_local_url_online
from app.utils.definitions import SERVER_URL
from app.utils.database.get import get_db
from app.utils.log import setup_custom_logger
from app.utils.server.api_calls_to_main import refresh_lock

global_username, global_email, global_pfp = None, None, None

router = APIRouter()

logger = setup_custom_logger(__name__)

thread_pool = ThreadPoolExecutor(
    max_workers=os.cpu_count() * 2)  # Manages multiple frontend requests efficiently

# Define an asynchronous lock to prevent simultaneous token refreshes

async def refresh_tokens(db: AsyncSession):
    refresh_token = await get_refresh_token(db)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token found, please log in")

    headers = {
        "refresh-token": f"{refresh_token}"
    }

    async with AsyncClient(timeout=120) as client:
        response = await client.post(f"{SERVER_URL}/refresh", headers=headers)

    if response.status_code == 200:
        tokens_dict = response.json()
        await set_access_token(tokens_dict["access_token"], db)
        await set_refresh_token(tokens_dict["refresh_token"], db)
        await set_url_token(tokens_dict["url_token"], db)
    else:
        raise HTTPException(status_code=401, detail="Token refresh failed")


@router.api_route("/main/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_request(request: Request, full_path: str, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    try:
        access_token = await get_access_token(db)
        if not access_token:
            raise HTTPException(status_code=401, detail="No token found, please log in")

        old_access_token = access_token

        headers = {
            "Authorization": f"Bearer {access_token}",
            **{key: value for key, value in request.headers.items() if key.lower() not in ["host", "authorization"]}
        }
        data = await request.body()
        params = dict(request.query_params)

        async def make_request(headers):
            async with AsyncClient(timeout=120) as client:
                req = client.build_request(
                    method=request.method,
                    url=f"{SERVER_URL}/{full_path}",
                    headers=headers,
                    content=data,
                    params=params
                )
                return await client.send(req)

        # Execute the request
        response = await make_request(headers)

        # Handle 401 Unauthorized response
        if response.status_code == 401:
            async with refresh_lock:
                # Recheck if tokens have been refreshed by another coroutine
                new_access_token = await get_access_token(db)
                if new_access_token == old_access_token:
                    # Refresh tokens since they are still old
                    await refresh_tokens(db)
                # Update headers with the new access token
                headers["Authorization"] = f"Bearer {await get_access_token(db)}"

            # Retry the request with new tokens
            response = await make_request(headers)

            if response.status_code == 401:
                raise HTTPException(status_code=401, detail="Unauthorized after token refresh")

        response.headers.pop("content-length", None)
        response.headers.pop("content-encoding", None)  # We handle the encoding in the response

        if response.headers.get("content-type", "").startswith("image"):
            return StreamingResponse(content=response.iter_bytes(), media_type=response.headers.get("content-type"),
                                     status_code=response.status_code, headers=dict(response.headers))

        try:
            json_content = response.json()
            if 'access_token' in json_content:
                await set_access_token(json_content['access_token'], db)
            if 'refresh_token' in json_content:
                await set_refresh_token(json_content['refresh_token'], db)
            if 'url_token' in json_content:
                await set_url_token(json_content['url_token'], db)

            json_content.pop('access_token', None)
            json_content.pop('refresh_token', None)

            return Response(content=json.dumps(json_content), media_type='application/json',
                            status_code=response.status_code, headers=dict(response.headers))
        except json.JSONDecodeError:
            return Response(content=response.content, media_type=response.headers.get('content-type'),
                            status_code=response.status_code, headers=dict(response.headers))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/online_login")
async def online_login(username: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    from server import localtunnel_url
    global global_username, global_email, global_pfp

    response = requests.post(f"{SERVER_URL}/login", data={"username": username, "password": password})
    if response.status_code == 200:
        tokens_dict = response.json()

        await set_access_token(tokens_dict["access_token"], db)
        await set_refresh_token(tokens_dict["refresh_token"], db)
        await set_url_token(tokens_dict["url_token"], db)
        # Get the online profile information
        try:
            global_username, global_email, global_pfp = await get_online_user_configuration()
        except Exception as e:
            logger.error(f"Error {e} getting online user configuration")
            global_username, global_email, global_pfp = (None, None, None)

        try:
            await set_local_url_online(localtunnel_url)  # Set the local URL online
        except Exception as e:
            logger.error(f"Error {e} setting local url online")
        return JSONResponse(content={"message": "Login successful", "access_token": tokens_dict["access_token"], "local_token_for_login": os.environ.get("LOCAL_TOKEN")})
    else:
        return JSONResponse(content={"message": f"Login failed, {response.content}"}, status_code=401)


@router.post("/online_logout")
async def online_logout(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    access_token = await get_access_token(db)
    refresh_token = await get_refresh_token(db)
    if not access_token or not refresh_token:
        return JSONResponse(content={"message": "No token found, please log in"}, status_code=401)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "refresh-token": f"{refresh_token}"
    }
    await set_access_token("", db)
    await set_refresh_token("", db)
    await set_url_token("", db)
    response = requests.post(f"{SERVER_URL}/logout", headers=headers)
    if response.status_code == 200:
        return JSONResponse(content={"message": "Logout successful"})
    else:
        return JSONResponse(content={"message": "Logout failed"}, status_code=401)


#@router.post("/set_tokens") not used
async def set_tokens(access_token: str = Form(...), refresh_token: str = Form(...), url_token: str = Form(...),
                     db: AsyncSession = Depends(get_db)):
    await set_access_token(access_token, db)
    await set_refresh_token(refresh_token, db)
    await set_url_token(url_token, db)

    return JSONResponse(content={"message": "Tokens set"})
