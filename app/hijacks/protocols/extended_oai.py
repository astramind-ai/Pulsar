from typing import Union, List, Optional, Dict, Any

import openai.types.chat
from pydantic import BaseModel
from vllm.entrypoints.openai.protocol import ChatCompletionRequest,    CustomChatCompletionMessageParam


class ExtendedCustomChatCompletionMessageParam(CustomChatCompletionMessageParam):
    id: Optional[int]


ChatCompletionMessageParam = Union[
    openai.types.chat.ChatCompletionMessageParam,
    CustomChatCompletionMessageParam,
    ExtendedCustomChatCompletionMessageParam
]


class ExtendedChatCompletionRequest(ChatCompletionRequest):
    messages: List[ChatCompletionMessageParam]
    personality_id: Optional[str] = None
    chat_id: Optional[str] = None
    system_prompt: Optional[str] = None
    pulsar_boost: Optional[bool] = None
    num_rollouts: Optional[int] = None
    chat_history_cutoff_percentage: Optional[float] = None
    max_depth: Optional[int] = None
    is_regeneration: Optional[bool] = None

    class Config:
        extra = "allow"

    def to_standard_request(self) -> ChatCompletionRequest:
        # Create a dictionary of all fields that are also in ChatCompletionRequest
        standard_fields = {}

        for field, value in self.model_dump().items():
            if field in ChatCompletionRequest.model_fields:
                standard_fields[field] = value

        if not standard_fields.get('tools', None) and standard_fields.get('tool_choice', 'none') == 'none':
            standard_fields.pop('tool_choice', None)
            standard_fields.pop('tools', None)
        if standard_fields.get('top_logprobs', 0) == 0 and not standard_fields.get('logprobs', False):
            standard_fields.pop('top_logprobs', None)
            standard_fields.pop('logprobs', None)
        # Handle messages conversion
        standard_fields['messages'] = self._convert_messages(self.messages)

        # Create and return a new ChatCompletionRequest
        return ChatCompletionRequest(**standard_fields)

    @staticmethod
    def _convert_messages(messages: List[ChatCompletionMessageParam]) -> List[Dict[str, Any]]:
        converted_messages = []
        for msg in messages:
            if isinstance(msg, (dict, BaseModel)):
                # Convert to dict if it's a Pydantic model
                msg_dict = msg.model_dump() if isinstance(msg, BaseModel) else msg
                # Remove 'id' if present (as it's not in standard ChatCompletionMessageParam)
                msg_dict.pop('id', None)
                msg_dict.pop('version', None)
                msg_dict.pop('parent_message_id', None)
                converted_messages.append(msg_dict)
            else:
                # If it's already in a format accepted by ChatCompletionRequest, use it as is
                converted_messages.append(msg)
        return converted_messages

