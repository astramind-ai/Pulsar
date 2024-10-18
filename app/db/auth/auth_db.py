import ipaddress
import os
import socket
import uuid
from typing import List, Tuple, Union, Optional, Dict

import jwt
from fastapi import Depends, HTTPException, status, Request
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.db_common import get_entity, oauth2_scheme
from app.db.db_setup import SessionLocal
from app.db.model.auth import User
from app.utils.database.get import get_db
from app.utils.decorators.cache import cache_unless_exception
from app.utils.definitions import SECRET_KEY, ALGORITHM, LOCAL_TOKEN
from app.utils.server.api_calls_to_main import make_api_request


# Setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

credential_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

@cache_unless_exception
async def validate_token(token: str = Depends(oauth2_scheme), ip: str = None):
    """
    Validate the provided JWT token and local token for same-machine requests.

    Args:
        token (str): The JWT token to validate.
        ip (str, optional): The IP address of the request, used for local token validation.

    Returns:
        str or dict: The username if valid or a dict for local users.

    Raises:
        HTTPException: If the token is invalid or does not match expected values.
    """
    from app.core.engine import async_engine_args
    try:
        # We check if the request is form a local ip address
        if is_from_local_network(ip):
            # we check if the token is the local token
            if token == LOCAL_TOKEN:
                return {"username": "local_user", "is_local": True}
            # we check if the user have chosen to allow local unauth request
            elif async_engine_args.allow_unsafe_local_requests:
                return {"username": "local_user", "is_local": True}
            else:
                # we try to decode the token
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                username: str = payload.get("sub")
                if username is None:
                    raise credential_exception
                return username

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credential_exception
        return username
    except jwt.PyJWTError:
        raise credential_exception

# User management functions
async def get_user(db: AsyncSession, username: str=None, return_all: bool = False) -> Optional[Union[User, List[User]]]:
    """
    Retrieve a user or a list of users from the database.

    Args:
        db (AsyncSession): The database session.
        username (str, optional): The username to query for.
        return_all (bool, optional): Flag to return all users if True.

    Returns:
        Optional[Union[User, List[User]]]: A single user or list of users depending on the return_all flag.
    """
    return await get_entity(db, User, name=username, return_all=return_all)


async def create_user(db: AsyncSession, username, image):
    """
    Create a new user entry in the database.

    Args:
        db (AsyncSession): The database session.
        username (str): The username for the new user.
        image (str): The image filename associated with the new user.

    Returns:
        User: The newly created user object.
    """
    db_user = User(id=str(uuid.uuid4()), name=username, image=image)
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user


async def authenticate_user(db: AsyncSession, username: str) -> Union[User, bool]:
    """
    Authenticate a user by checking if the username exists in the database.

    Args:
        db (AsyncSession): The database session.
        username (str): The username to authenticate.

    Returns:
        Union[User, bool]: The user object if authentication is successful, False otherwise.
    """
    user = await get_user(db, username)
    return user or False


async def set_last_model_lora(db: AsyncSession, current_user: User, model_id: str=None, lora_id: str=None):
    """
    Set the last used model and LoRa IDs for a user.

    Args:
        db (AsyncSession): The database session.
        current_user (User): The current user whose record is to be updated.
        model_id (str, optional): The model ID to set.
        lora_id (str, optional): The LoRA ID to set.

    """
    user = await get_user(db, current_user.name)
    if model_id is not None:
        users = await get_user(db, return_all=True) # the model is set for all users
        for user_ in users:
            user_.last_model = model_id
    if lora_id is not None:
        user.last_lora = lora_id
    await db.commit()


async def get_last_model_lora(db: AsyncSession, current_user: User) -> Dict:
    """
    Retrieve the last used model and LoRa IDs for a user.

    Args:
        db (AsyncSession): The database session.
        current_user (User): The user whose IDs are to be retrieved.

    Returns:
        Dict: A dictionary containing 'model' and 'lora' keys with corresponding IDs.
    """
    user = await get_user(db, current_user.name)
    return {'model': user.last_model, 'lora': user.last_lora}


# Token management function
def create_access_token(data: dict) -> str:
    """
    Create a JWT access token using the provided data.

    Args:
        data (dict): The data to encode in the JWT.

    Returns:
        str: The encoded JWT token.
    """
    to_encode = data.copy()
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)



def get_allowed_networks() -> List[ipaddress.IPv4Network]:
    """
    Get a list of allowed network ranges, including Docker internal network if specified.

    Returns:
        List[ipaddress.IPv4Network]: List of allowed network ranges.
    """
    allowed_networks = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
    ]

    docker_internal = os.environ.get("DOCKER_INTERNAL_NETWORK")
    if docker_internal:
        try:
            allowed_networks.append(ipaddress.ip_network(docker_internal))
        except ValueError:
            print(f"Warning: Invalid DOCKER_INTERNAL_NETWORK value: {docker_internal}")

    return allowed_networks


def get_localhost_addresses() -> List[str]:
    """
    Retrieve a list of IP addresses associated with the localhost.

    Returns:
        List[str]: A list of localhost IP addresses.
    """
    localhost_addresses = [
        "127.0.0.1",
        "::1",
        "0:0:0:0:0:0:0:1",
        "localhost"
    ]
    try:
        local_hostname = socket.gethostname()
        localhost_addresses.append(socket.gethostbyname(local_hostname))
    except socket.gaierror:
        pass
    return localhost_addresses


def is_allowed_request(client_ip: str) -> bool:
    """
    Check if a request is allowed based on its IP address.

    This function checks if the request is from localhost, same machine,
    or an allowed network (including Docker internal network if specified).

    Args:
        client_ip (str): The IP address of the incoming request.

    Returns:
        bool: True if the request is allowed, False otherwise.
    """
    # Check for localhost and same machine
    if client_ip in get_localhost_addresses():
        return True

    try:
        ip = ipaddress.ip_address(client_ip)

        # Check for IPv4 private networks
        if ip.version == 4:
            return any(ip in network for network in get_allowed_networks())

        # Check for IPv6 Unique Local Addresses
        elif ip.version == 6:
            return ip in ipaddress.ip_network("fd00::/8")

    except ValueError:
        # If the IP address is invalid, return False
        return False

    return False


async def ensure_local_request(request: Request):
    """
    Ensure that the incoming request is from an allowed source.

    This function checks if the request is from localhost, same machine,
    Docker internal network, or a valid local network (when using host networking).

    Args:
        request (Request): The incoming request object.

    Raises:
        HTTPException: If the request is not from an allowed source.
    """
    client_host = request.client.host

    if is_allowed_request(client_host):
        return True

    # If the request is not from an allowed source, raise an exception
    raise HTTPException(status_code=403, detail="Access denied. Request not from an allowed source.")


# Update these functions to use the new unified check
def is_from_local_network(client_ip: str) -> bool:
    return is_allowed_request(client_ip)


async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Retrieve the current authenticated user based on the provided token.

    Args:
        token (str): The access token.

    Returns:
        User: The authenticated user object.

    Raises:
        HTTPException: If the user cannot be authenticated.
    """
    username = await validate_token(token)
    async with SessionLocal() as db:
        user = await get_user(db, username=username)
        if user is None:
            raise credential_exception
        return user

async def get_current_user_for_login(request: Request, token: str = Depends(oauth2_scheme)):
    """
    Retrieve the current authenticated user based on the provided token.

    Args:
        token (str): The access token.
        request (Request): The incoming request object.

    Returns:
        User: The authenticated user object.

    Raises:
        HTTPException: If the user cannot be authenticated.
    """
    if not token == os.environ.get("LOCAL_TOKEN") and not is_from_local_network(request.client.host):
        raise credential_exception


async def auth_user_with_local_exception(request: Request, token: str = Depends(oauth2_scheme)):
    """
    Authenticate a user or handle local user exceptions based on the incoming request and token.

    Args:
        request (Request): The incoming request object.
        token (str): The access token.

    Raises:
        HTTPException: If the user cannot be authenticated.
    """
    username = await validate_token(token, request.client.host)
    if isinstance(username,dict) and username.get('username') == "local_user" and username.get('is_local'):
        return
    async with SessionLocal() as db:
        user = await get_user(db, username=username)
        if user is None:
            raise credential_exception
        return user


# Online user configuration
async def get_online_user_configuration() -> Tuple[str, str, str]:
    """
    Retrieve the online configuration for a user from the main API.

    Returns:
        Tuple[str, str, str]: A tuple containing username, email, and image URL.
    """
    async for db in get_db():
        response_json = await make_api_request(db, "GET", "/users/me")

    return response_json['username'], response_json['email'], response_json['pfp']  # noqa
