import uuid
from typing import Union, AsyncGenerator, Optional

from starlette.requests import Request
from vllm.entrypoints.openai.protocol import ErrorResponse, ChatCompletionResponse
from vllm.entrypoints.openai.serving_chat import OpenAIServingChat

from app.hijacks.protocols.extended_oai import ExtendedChatCompletionRequest
from app.utils.formatting.chat.formatter import extract_parameter_from_request
from app.utils.log import setup_custom_logger
from app.services.logic_booster.pulsar_boost import PulsarBoost

logger = setup_custom_logger(__name__)


class ExtendedOpenAIServingChat(OpenAIServingChat):
    def __init__(self, api_url, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pulsar_boost_solver = PulsarBoost(api_url, self.model_config.model)

    async def create_pulsar_chat_completion(
            self,
            request: ExtendedChatCompletionRequest,
            raw_request: Optional[Request] = None,
    ) -> Union[AsyncGenerator[str, None], ChatCompletionResponse, ErrorResponse]:
        request.truncate_prompt_tokens = float(
            request.chat_history_cutoff_percentage / 100)  # this set the "history" if the user does not set it himself
        return await super().create_chat_completion(request, raw_request)

    async def stream_chat_completion_with_rstar(
            self,
            request: ExtendedChatCompletionRequest,

    ) -> Union[ErrorResponse, AsyncGenerator[str, None], ChatCompletionResponse]:
        try:
            request_id = f'chat-{uuid.uuid4()}'

            return self.pulsar_boost_solver.process(
                request,
                request_id,

            )

        except Exception as e:
            logger.error(f"Error in streaming results: {str(e)}")
            return self.create_error_response(str(e))

    async def generate_response(
            self,
            request: ExtendedChatCompletionRequest,
            raw_request: Optional[Request] = None,
    ) -> Union[ErrorResponse, AsyncGenerator[str, None], ChatCompletionResponse]:
        (is_pulsar_boost, _) = await extract_parameter_from_request(request, ['pulsar_boost', ])
        if is_pulsar_boost:
            return await self.stream_chat_completion_with_rstar(request)
        return await super().create_chat_completion(request, raw_request)
