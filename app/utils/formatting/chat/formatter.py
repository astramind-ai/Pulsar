
from vllm.entrypoints.openai.protocol import ChatCompletionRequest

from app.utils.log import setup_custom_logger

logger = setup_custom_logger(__name__)


async def format_chat_request(request: ChatCompletionRequest) -> dict:
    """
    Format a dict request to a string
    :param request:
    :return:
    """
    request_dict = request.model_dump().copy()
    request_dict.pop("messages")
    request_dict.pop('model')
    request_dict.pop("user")
    request_dict.pop("response_format")
    request_dict['stop'] = str(request_dict.get('stop', ''))
    request_dict['stop_token_ids'] = str(request_dict.get('stop_token_ids', ''))
    return request_dict


async def format_chat_response(response: dict) -> dict:
    """
    Format a response dict to a string
    :param response:
    :return:
    """
    response_dict = response.copy()
    resonse_text = response_dict['choices'][0]['message']['content']

    return {"role": "assistant", "content": resonse_text}


async def extract_parameter_from_request(request: ChatCompletionRequest, parameters: list) -> tuple:
    """
    Extract list of parameters from a request
    :param request:
    :param parameters:
    :return:
    """
    request_dict = await format_chat_request(request)
    extracted_params = tuple(request_dict.pop(param, '') for param in parameters)
    return *extracted_params, request_dict
