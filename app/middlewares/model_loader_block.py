import threading

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

block_requests = False
lock = threading.Lock()


class BlockRequestsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        global block_requests
        with lock:
            if block_requests:
                return JSONResponse(content={
                    "detail": "Server is not accepting requests, a restart is about to happen try again in a minute "
                              "or so"},
                    status_code=503)
        response = await call_next(request)
        return response


def set_block_requests(value: bool):
    global block_requests
    with lock:
        block_requests = value
