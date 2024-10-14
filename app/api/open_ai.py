import asyncio
import tempfile
from typing import Optional, Set

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from typing_extensions import assert_never
from vllm.config import ModelConfig
from vllm.engine.arg_utils import AsyncEngineArgs
from vllm.entrypoints.openai.protocol import (ChatCompletionRequest,
                                              ChatCompletionResponse,
                                              CompletionRequest,
                                              DetokenizeRequest,
                                              DetokenizeResponse,
                                              EmbeddingRequest,
                                              EmbeddingResponse, ErrorResponse,
                                              TokenizeRequest,
                                              TokenizeResponse,
                                              )
# yapf: enable
from vllm.entrypoints.openai.serving_chat import OpenAIServingChat
from vllm.entrypoints.openai.serving_completion import OpenAIServingCompletion
from vllm.entrypoints.openai.serving_embedding import OpenAIServingEmbedding
from vllm.entrypoints.openai.serving_tokenization import (
    OpenAIServingTokenization)
from vllm.logger import init_logger

from app.db.auth.auth_db import auth_user_with_local_exception
from app.db.model.auth import User

TIMEOUT_KEEP_ALIVE = 5  # seconds

engine_args: AsyncEngineArgs
openai_serving_chat: OpenAIServingChat
openai_serving_completion: OpenAIServingCompletion
openai_serving_embedding: OpenAIServingEmbedding
openai_serving_tokenization: OpenAIServingTokenization
prometheus_multiproc_dir: tempfile.TemporaryDirectory

# Cannot use __name__ (https://github.com/vllm-project/vllm/pull/4765)
logger = init_logger('vllm.entrypoints.openai.api_server')

_running_tasks: Set[asyncio.Task] = set()


def load_serving_entrypoints() -> None:
    global openai_serving_chat, openai_serving_completion, openai_serving_embedding, openai_serving_tokenization
    from app.core.engine import openai_serving_tokenization, openai_serving_chat, openai_serving_embedding
    openai_serving_tokenization, openai_serving_chat, openai_serving_embedding = (
        openai_serving_tokenization, openai_serving_chat, openai_serving_embedding)


def model_is_embedding(model_name: str, trust_remote_code: bool,
                       quantization: Optional[str]) -> bool:
    return ModelConfig(model=model_name,
                       tokenizer=model_name,
                       tokenizer_mode="auto",
                       trust_remote_code=trust_remote_code,
                       quantization=quantization,
                       seed=0,
                       dtype="auto").embedding_mode


router = APIRouter()


@router.post("/tokenize")
async def tokenize(request: TokenizeRequest, current_user: User = Depends(auth_user_with_local_exception)):
    generator = await openai_serving_tokenization.create_tokenize(request)
    if isinstance(generator, ErrorResponse):
        return JSONResponse(content=generator.model_dump(),
                            status_code=generator.code)
    elif isinstance(generator, TokenizeResponse):
        return JSONResponse(content=generator.model_dump())

    assert_never(generator)


@router.post("/detokenize")
async def detokenize(request: DetokenizeRequest, current_user: User = Depends(auth_user_with_local_exception)):
    generator = await openai_serving_tokenization.create_detokenize(request)
    if isinstance(generator, ErrorResponse):
        return JSONResponse(content=generator.model_dump(),
                            status_code=generator.code)
    elif isinstance(generator, DetokenizeResponse):
        return JSONResponse(content=generator.model_dump())

    assert_never(generator)


@router.post("/v1/chat/completions")
async def create_chat_completion(request: ChatCompletionRequest,
                                 raw_request: Request, current_user: User = Depends(auth_user_with_local_exception)):
    generator = await openai_serving_chat.create_chat_completion(
        request, raw_request)

    if isinstance(generator, ErrorResponse):
        return JSONResponse(content=generator.model_dump(),
                            status_code=generator.code)

    elif isinstance(generator, ChatCompletionResponse):
        return JSONResponse(content=generator.model_dump())

    return StreamingResponse(content=generator, media_type="text/event-stream")


@router.post("/v1/completions")
async def create_completion(request: CompletionRequest, raw_request: Request,
                            current_user: User = Depends(auth_user_with_local_exception)):
    return HTTPException(status_code=501, detail="Developers should use the /v1/chat/completions endpoint instead.")


@router.post("/v1/embeddings")
async def create_embedding(request: EmbeddingRequest, raw_request: Request,
                           current_user: User = Depends(auth_user_with_local_exception)):
    generator = await openai_serving_embedding.create_embedding(
        request, raw_request)
    if isinstance(generator, ErrorResponse):
        return JSONResponse(content=generator.model_dump(),
                            status_code=generator.code)
    elif isinstance(generator, EmbeddingResponse):
        return JSONResponse(content=generator.model_dump())

    assert_never(generator)
