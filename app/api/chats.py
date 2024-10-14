import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import JSONResponse
from vllm.entrypoints.openai.protocol import ErrorResponse, CompletionRequest

from app.db.auth.auth_db import get_current_user
from app.db.chat.chat_db import async_unpack_chat_history
from app.db.lora.lora_db import establish_if_lora
from app.db.ml_models.model_db import get_current_model
from app.db.model.auth import User
from app.db.model.chat import Chat, Message
from app.db.personality.personality_db import format_dict_to_string, get_personality_by_id
from app.hijacks.protocols.extended_oai import ExtendedChatCompletionRequest
from app.hijacks.starlette import WrappedStreamingResponse
from app.utils.formatting.chat.formatter import format_chat_response, extract_parameter_from_request
from app.utils.formatting.chat.summerizer import populate_and_summarize_chat
from app.utils.database.get import get_db
from app.utils.formatting.personality.personality_preprompt import format_personality_preprompt
from app.utils.log import setup_custom_logger

router = APIRouter()

logger = setup_custom_logger(__name__)


@router.put("/v1/chat/edit")
async def edit_message(chat_id: str, summary: str,
                       request: Request, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    message = await db.execute(select(Chat).where(Chat.id == chat_id))
    message = message.scalars().first()
    if not message:
        raise HTTPException(detail="No message found with this ID.", status_code=404)
    if message.user_id != current_user.id:
        raise HTTPException(detail="You are not the owner of this message.", status_code=403)
    message.summary = summary
    await db.commit()
    return JSONResponse(content={"message": f"Message {chat_id} edited"})


@router.delete("/v1/chat/delete")
async def delete_message(chat_id: str, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    message = await db.execute(select(Chat).where(Chat.id == chat_id))
    message = message.scalars().first()
    if not message:
        raise HTTPException(detail="No message found with this ID.", status_code=404)
    if message.user_id != current_user.id:
        raise HTTPException(detail="You are not the owner of this message.", status_code=403)
    await db.delete(message)
    await db.commit()
    return JSONResponse(content={"message": f"Message {chat_id} deleted"})


@router.delete("/abort/{message_id}")
async def abort(message_id: str):
    from app.core.engine import openai_serving_chat
    # the id here is from the stream response
    await openai_serving_chat.engine_client.abort(message_id)
    return JSONResponse(content={"message": f"Message {message_id} aborted"})


@router.get("/v1/list/chats")
async def list_chats(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    chats = await db.execute(select(Chat).where(Chat.user_id == current_user.id))
    chats = chats.scalars().all()
    return JSONResponse(
        content=[{"chat_id": chat.id, "summary": chat.summary, "timestamp": chat.timestamp.strftime("%Y%m%d%H%M%S")} for
                 chat in chats])


@router.get("/v1/chat/history")
async def get_chat_history(request: Request, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user)):  # noqa
    chat_id = request.query_params.get('chat_id', None)
    if not chat_id:
        raise HTTPException(detail="chat_id is required", status_code=400)
    try:
        history = await async_unpack_chat_history(db, chat_id, full_history=True)
        return JSONResponse(content=history, status_code=200)
    except Exception as e:
        HTTPException(detail=str(e), status_code=500)


@router.post("/v1/chat/pulsar/completions")
async def create_chat_completion(
        request: ExtendedChatCompletionRequest,
        raw_request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    from app.core.engine import openai_serving_chat
    from app.api.loras import lora_chat_template_dict

    (chat_id, personality_id, is_regeneration,
     selected_messages_version_ids, sys_prompt,
     request_dict) = await extract_parameter_from_request(request, ["chat_id", "personality_id",
                                                                    "is_regeneration",
                                                                    'selected_messages_version_ids',
                                                                    'system_prompt', ])

    if personality_id:
        personality = await get_personality_by_id(db, personality_id, current_user.id)
    else:
        personality = None

    model = await get_current_model(db)

    is_new_chat = False

    # Retrieve or initialize chat
    if chat_id:
        chat = await db.execute(select(Chat).where(Chat.id == chat_id))
        chat = chat.scalars().first()
        if not chat:
            raise HTTPException(detail="No chat found with this ID.", status_code=404)
    else:
        chat_id = uuid.uuid4().hex
        chat = Chat(id=chat_id, user_id=current_user.id, model_id=model.name, timestamp=func.now())
        db.add(chat)

        is_new_chat = True

    # Check model compatibility
    is_lora = await establish_if_lora(request.model, db)
    if not is_lora and (model.url != request.model):
        raise HTTPException(detail=f"Wrong model selected, the current loaded model is {model.name}",
                            status_code=400)

    if is_lora:
        request.chat_template = lora_chat_template_dict.get(request.model, None)

    message = request.messages[0]

    # add system prompt if in personality chat
    if is_new_chat:

        # message = await personality_message_hijack(message, context)
        if sys_prompt != '':
            initial_content = request.system_prompt.replace("{{personality_name}}", personality.name).replace(
                "{{current_user}}", current_user.name).replace("{{personality_attributes}}",
                                                                   format_dict_to_string(personality.pre_prompt)) \
                                                                   if personality else request.system_prompt
        else:
            initial_content = await format_personality_preprompt(personality, current_user) \
                if personality else "You are an helpful AI Assistant."
        system_message = Message(chat=chat, id=message["parent_message_id"], model_id=model.name,
                                 content={"content": initial_content, "role": "system"})

        db.add(system_message)

    if not is_regeneration:
        if isinstance(message['content'], list):
            message['content'] = "<_MultiModalContent_>" + json.dumps(
                message['content'])  # we add a prefix to the message to identify it as multimodal

        user_message = Message(chat=chat, id=message['id'],
                               parent_message_id=message["parent_message_id"], model_id=model.name,
                               content={"content": message['content'], "role": message['role']})
        db.add(user_message)

    # Finalize chat session
    await db.commit()

    unpacked_history = await async_unpack_chat_history(db, chat, message["id"], selected_messages_version_ids,
                                                       personality)
    request.messages = unpacked_history
    response_id = uuid.uuid4().hex
    try:
        generator = await openai_serving_chat.generate_response(request, raw_request)
        if isinstance(generator, ErrorResponse):
            return JSONResponse(content=generator.model_dump(), status_code=generator.code)
        if request.stream:
            return WrappedStreamingResponse(generator, db, chat, response_id, message['id'], model.name,
                                            media_type="text/event-stream")

        response = await format_chat_response(generator.model_dump())
        response_msg = Message(chat=chat, id=response_id, parent_message_id=message['id'], model_id=model.name,
                               content=response)
        db.add(response_msg)
        await db.commit()
        generation = generator.model_dump()
        generation['chat_id'] = chat_id
        generation['id'] = response_id
        return JSONResponse(content=generation)
    except Exception as e:
        await db.rollback()
        raise HTTPException(detail=str(e), status_code=500)
    finally:
        if is_new_chat:
            try:
                await populate_and_summarize_chat(chat, db, openai_serving_chat, request, raw_request)
            except Exception as e:
                logger.error(f"Error while summarizing chat: {e}")


@router.post("/v1/completions")
async def create_completion(request: CompletionRequest, raw_request: Request, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    """
    ATM non-functioning. This is a placeholder for the future.
    """
    raise HTTPException(detail="Not implemented yet", status_code=501)
