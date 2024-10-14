from functools import wraps

import cachetools
from fastapi import Depends

from app.db.db_common import oauth2_scheme
from app.utils.definitions import ACCESS_TOKEN_EXPIRE_MINUTES

cache = cachetools.TTLCache(maxsize=1024, ttl=ACCESS_TOKEN_EXPIRE_MINUTES)


def cache_unless_exception(func):
    @wraps(func)
    async def wrapper(token: str = Depends(oauth2_scheme), ip: str = None):
        try:
            # generate a unique key for the function call
            key = cachetools.keys.hashkey(token)

            # try to get the result from the cache
            if key in cache:
                return cache[key]

            # if the result is not in the cache, call the function
            result = await func(token, ip)

            # memorize the result in the cache
            cache[key] = result
            return result
        except Exception as e:
            # if an exception is raised, raise it without caching
            raise e
    return wrapper
