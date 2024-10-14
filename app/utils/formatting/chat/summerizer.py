from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from vllm.entrypoints.openai.protocol import ChatCompletionRequest
from vllm.entrypoints.openai.serving_chat import OpenAIServingChat

from app.db.model.chat import Chat
from app.utils.definitions import SUMMARIZATION_TEMPLATE


async def summarize(summerizer_request: ChatCompletionRequest, raw_request: Request, chat_completor: OpenAIServingChat):
    summerizer_request.stream = False
    return await chat_completor.create_chat_completion(summerizer_request, raw_request)


async def populate_and_summarize_chat(chat: Chat, db: AsyncSession, chat_completor: OpenAIServingChat,
                                      request: ChatCompletionRequest, raw_request: Request):
    """
    This function simulates the process of populating a chat with messages and then summarizing the chat.

    """
    first_user_message = next((msg.content['content'] for msg in chat.messages if msg.content['role'] == 'user'), None)
    summarizer_chat = [{'content': 'You are a very helpful and skilled summerizer,'
                                   'You need to briefly summerize the user text in 3/5 words, i.e: Tell me recepie '
                                   'for a pumpkin pie -> Pumpkin Pie Recepie ',
                        'role': 'system'},
                       {'content': SUMMARIZATION_TEMPLATE.format(first_user_message=first_user_message),
                        'role': 'user'}]
    request = request.model_copy()
    request.temperature = 0.7
    request.max_tokens = 10
    request.top_k = -1
    request.top_p = 0.1
    request.repetition_penalty = 1.0
    request.messages = summarizer_chat

    summary = await summarize(request, raw_request, chat_completor)

    # Update the chat summary
    chat.summary = summary.choices[0].message.content
    await db.commit()
