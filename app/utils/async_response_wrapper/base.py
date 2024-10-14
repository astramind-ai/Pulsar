import json
from typing import Optional, AsyncGenerator, Dict, Any
from app.utils.log import setup_custom_logger

import aiohttp
from vllm.entrypoints.openai.protocol import (
    ChatCompletionStreamResponse,
    ChatCompletionResponseStreamChoice,
    DeltaMessage, ChatCompletionRequest
)

from app.db.auth.auth_db import LOCAL_TOKEN


# Base class for handling asynchronous API responses which needs to make internal API calls
class BaseAsyncResponseWrapper:
    def __init__(self, api_base_url: str, model_name: str):
        self.model_name = model_name
        self.api_base_url = api_base_url
        self.api_url = self.api_base_url + "/v1/chat/completions"
        self.token = LOCAL_TOKEN
        self.logger = setup_custom_logger(f"{__name__}.{self.__class__.__name__}")
        self.general_request: Optional[ChatCompletionRequest] = None
        self.starting_message = 'INTERNAL-'

    # Main method to make API calls
    async def api_call(self, chat_completion_request: ChatCompletionRequest) -> AsyncGenerator[Dict[str, Any], None]:
        chat_completion_request.model = f'{self.model_name}'
        self.logger.debug(f"Sending request to {self.api_url}")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    self.api_url,
                    json=self._chat_request_to_dict(chat_completion_request),
                    headers={"Content-Type": "application/json",
                             "Authorization": f"Bearer {self.token}"}
            ) as response:
                if chat_completion_request.stream:
                    # Handle streaming response
                    async for line in response.content:
                        if line.startswith(b'data: '):
                            if line.strip() == b'data: [DONE]':
                                break
                            try:
                                yield json.loads(line.decode('utf-8').strip()[6:])
                            except json.JSONDecodeError:
                                continue
                else:
                    # Handle non-streaming response
                    yield await response.json()

    # Update chat request with new parameters
    def _update_chat_request(self, *args, **kwargs) -> ChatCompletionRequest:
        request_copy = self.general_request.model_copy()
        request_copy.guided_decoding_backend = 'outlines'
        request_copy.max_tokens = None
        for var in kwargs:
            if hasattr(request_copy, var):
                setattr(request_copy, var, kwargs[var])
        return request_copy

    # Convert ChatCompletionRequest to dictionary
    @staticmethod
    def _chat_request_to_dict(request: ChatCompletionRequest) -> dict:

        request_dict = dict()

        # Add required fields
        request_dict['messages'] = request.messages
        request_dict['model'] = request.model

        # Add optional fields
        optional_fields = ChatCompletionRequest.__annotations__.keys()

        for field in optional_fields:
            value = getattr(request, field)
            if value is not None and value != request.model_fields[field].default:
                request_dict[field] = value

        # Special handling for fields with complex types
        if request_dict.get('response_format'):
            request_dict['response_format'] = request_dict['response_format'].dict()

        if request_dict.get('stream_options'):
            request_dict['stream_options'] = request_dict['stream_options'].dict()

        if request_dict.get('tools'):
            request_dict['tools'] = [tool.dict() for tool in request_dict['tools']]

        if isinstance(request_dict.get('tool_choice'), dict):
            request_dict['tool_choice'] = request_dict['tool_choice'].dict()

        return request_dict

    # Create a stream response
    def _create_stream_response(self, content: str, request_id: str, created_time: int,
                                finish_reason: Optional[str] = None) -> str:
        choice_data = ChatCompletionResponseStreamChoice(
            index=0,
            delta=DeltaMessage(content=self.starting_message + content if finish_reason != 'stop' else content),
            logprobs=None,
            finish_reason=finish_reason
        )
        chunk = ChatCompletionStreamResponse(
            id=request_id,
            object="chat.completion.chunk",
            created=created_time,
            choices=[choice_data],
            model=f'pulsar-boosted-{self.model_name}',
        )
        return f"data: {chunk.model_dump_json(exclude_unset=True)}\n\n"


