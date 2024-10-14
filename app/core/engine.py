import asyncio
import copy
import gc
from typing import Optional, Union

import torch
#from faster_whisper import WhisperModel
from vllm import AsyncLLMEngine
from vllm.config import ModelConfig
from vllm.entrypoints.openai.serving_completion import OpenAIServingCompletion
from vllm.entrypoints.openai.serving_embedding import OpenAIServingEmbedding
from vllm.entrypoints.openai.serving_engine import BaseModelPath
from vllm.entrypoints.openai.serving_tokenization import OpenAIServingTokenization
from vllm.usage.usage_lib import UsageContext

from .fallback.picker import pick_a_quantized_fallback
from .whisper import get_optimal_whisper
from ..hijacks.openai import ExtendedOpenAIServingChat
from ..hijacks.vllm import ExtendedAsyncEngineArgs, ExtendedAsyncCompleteServerArgs
from ..utils.log import setup_custom_logger
from ..utils.models.tokenizer_template_inferrer import maybe_get_chat_template
from ..utils.server.engine_utils import find_max_seq_len

# Global variables
#transcriber: Optional[WhisperModel] = None
openai_serving_chat: Optional[ExtendedOpenAIServingChat] = None
openai_serving_completion: Optional[OpenAIServingCompletion] = None
openai_serving_embedding: Optional[OpenAIServingEmbedding] = None
openai_serving_tokenization: Optional[OpenAIServingTokenization] = None
async_engine: Optional[AsyncLLMEngine] = None
async_engine_args: Optional[ExtendedAsyncEngineArgs] = None
model_config: Optional[ModelConfig] = None
is_lora_enabled: Optional[bool] = None
is_model_vision: Optional[bool] = None
images_per_prompt: Optional[int] = None

logger = setup_custom_logger(__name__)


def delete_engine_model_from_vram() -> None:
    """Delete the model and all the gc's references to free the VRAM."""
    global async_engine, openai_serving_chat, openai_serving_completion
    logger.debug("Deleting the engine and all the gc's references to free the VRAM")
    try:
        del async_engine.engine.model_executor.driver_worker.model_runner
        del async_engine.engine.model_executor.driver_worker
        del async_engine
        del openai_serving_chat, openai_serving_completion
    except AttributeError:  # already unloaded
        pass
    gc.collect()
    torch.cuda.synchronize()
    torch.cuda.empty_cache()


def get_engine_args(args: Union[dict, ModelConfig]) -> Optional[ExtendedAsyncEngineArgs]:
    """Get engine arguments from either a dictionary or ModelConfig object."""
    if isinstance(args, dict):
        return ExtendedAsyncEngineArgs(**args)
    elif isinstance(args, ModelConfig):
        return ExtendedAsyncEngineArgs.from_model_conf(vars(args))
    return None


async def initialize_transcriber() -> None:
    """Initialize the transcriber. Not implemented in this version."""
    global transcriber
    logger.info("Initializing the transcriber")
    transcriber = get_optimal_whisper()


async def initialize_engine(engine_args: ExtendedAsyncEngineArgs, usage_context: UsageContext.ENGINE_CONTEXT) -> None:
    """Initialize the engine with the given arguments."""
    global async_engine, model_config, async_engine_args, is_lora_enabled, is_model_vision, images_per_prompt
    async_engine = None
    async_engine_args = engine_args

    retries = 0
    original_engine_args = copy.copy(engine_args)
    while not async_engine and retries <= 3:
        try:
            async_engine = AsyncLLMEngine.from_engine_args(engine_args, usage_context=usage_context)
            tokenizer = await async_engine.get_tokenizer()
            if not tokenizer.chat_template:
                async_engine = None  # to throw AttributeError and to not delete the variable
                raise RuntimeError(
                    "Chat template is not defined in the tokenizer, this is probably not an instruction tuned model. "
                    "Please use another model"
                )
            try:
                model_config = await async_engine.get_model_config()
            except RuntimeError:  # Handle if not within an async context
                model_config = asyncio.run(async_engine.get_model_config())

        except (torch.cuda.OutOfMemoryError, RuntimeError, ValueError) as e:
            if retries < 3:
                if await handle_specific_errors(e, engine_args):
                    continue
                log_message = f"Failed to initialize the engine due to: {str(e)}. Retry {retries + 1}"
                logger.error(log_message)
                delete_engine_model_from_vram()
                if isinstance(e, torch.cuda.OutOfMemoryError):
                    if not engine_args.max_model_len:
                        # we do this so that at the next iter we can try to auto gauge the max_model_len
                        engine_args.max_model_len = 32768
                    else:
                        engine_args.max_model_len = min(int(engine_args.max_model_len / 2), 8172)
                    if retries < 4:
                        retries += 1
                        continue  # continue without decreasing the gpu mem utilization

                engine_args.gpu_memory_utilization = engine_args.gpu_memory_utilization - 0.1
                engine_args.swap_space += 2
            else:
                handle_final_retry(engine_args, original_engine_args, e)
            retries += 1
            continue  # Continue to retry initialization

        except Exception as e:
            logger.error(f"Failed to initialize the engine due to: {str(e)}")
            raise RuntimeError(f"Failed to initialize the engine due to: {str(e)}") from e

        if async_engine:
            is_lora_enabled = engine_args.enable_lora
            is_model_vision = async_engine.engine.model_config.multimodal_config is not None
            images_per_prompt = (
                async_engine.engine.model_config.multimodal_config.limit_per_prompt.get("image", 0)
                if is_model_vision
                else 0
            )
        break  # Break the loop if engine is initialized successfully

    if not async_engine:
        logger.error(
            f"Model {engine_args.model} is too big for your current setup, "
            f"please choose a quantized version or try with a different model"
        )
        raise RuntimeError(
            f"Model {engine_args.model} is too big for your current setup, "
            f"please choose a quantized version or try with a different model"
        )


async def handle_specific_errors(e: Exception, engine_args: ExtendedAsyncEngineArgs) -> bool:
    """Handle specific errors during engine initialization."""
    if any(sub_string in str(e) for sub_string in ['max_num_batched_tokens', 'does not support LoRA']):
        engine_args.enable_lora = False
        logger.error("Due to vllm kernel limitations, lora will be disabled for this model")
        delete_engine_model_from_vram()
        return True
    elif 'multimodal models' in str(e):
        engine_args.limit_mm_per_prompt = None
        logger.info("The previous configuration was for a MultiModal LLM, correcting configuration and retrying.")
        delete_engine_model_from_vram()
        return True
    elif 'is greater than the derived max_model_len' in str(e):
        max_context_len = find_max_seq_len(str(e))
        if max_context_len:
            logger.error(f"{str(e).split('.')[0]}. Automatically changing max_model_len to {max_context_len}")
            engine_args.max_model_len = max_context_len
            delete_engine_model_from_vram()
            return True
    elif "The model's max seq len" in str(e):
        max_context_len = find_max_seq_len(str(e))
        if max_context_len:
            logger.error(f"{str(e).split('.')[0]}. Automatically changing max_model_len to {max_context_len}")
            engine_args.max_model_len = max_context_len
            delete_engine_model_from_vram()
            return True
    elif 'Chat template is not defined in the tokenizer' in str(e):
        logger.error("Chat template is not defined in the tokenizer, we'll to try infer it from the model config, this could lead to misconfigurations")
        model_template = await maybe_get_chat_template(engine_args.model)
        if not model_template:
            raise RuntimeError("Chat template is not defined in the tokenizer, "
                           "this is probably not an instruction tuned model.  Please use another model") from e
        engine_args.chat_template = model_template
        return True
    elif 'No available memory for the cache blocks' in str(e):
        max_context_len = int((engine_args.max_model_len or 65536) / 4)
        logger.error(f"{str(e).split('.')[0]}. Automatically changing max_model_len to {max_context_len}")
        engine_args.max_model_len = max_context_len
        delete_engine_model_from_vram()
        return True
    return False


def handle_final_retry(engine_args: ExtendedAsyncEngineArgs,
                       original_engine_args: ExtendedAsyncEngineArgs,
                       e: Exception) -> None:
    """Handle the final retry attempt."""
    if engine_args.auto_quantized_fallback:
        engine_args.model = pick_a_quantized_fallback(engine_args.quant_type_preference)
        engine_args = original_engine_args
    else:
        logger.error(f"Unable to initialize model after retries: {str(e)}")
        raise RuntimeError(f"Unable to initialize model after retries: {str(e)}") from e


def create_serving_instances(models: list, args: ExtendedAsyncCompleteServerArgs) -> None:
    """Create the serving instances for chat and completion."""
    global openai_serving_chat, openai_serving_completion, openai_serving_embedding, openai_serving_tokenization
    served_model = [BaseModelPath(model_path='', name=model) for model in models]
    openai_serving_chat = ExtendedOpenAIServingChat(
        api_url=f"http://{args.host}:{args.port}",
        engine_client=async_engine,
        model_config=model_config,
        base_model_paths= served_model,
        response_role=args.response_role,
        lora_modules=args.lora_modules,
        chat_template=args.chat_template,
        prompt_adapters=None,
        request_logger=None
    )
    openai_serving_embedding = OpenAIServingEmbedding(
        engine_client=async_engine,
        model_config=model_config,
        base_model_paths= served_model,
        request_logger=None
    )
    openai_serving_tokenization = OpenAIServingTokenization(
        engine_client=async_engine,
        model_config=model_config,
        base_model_paths= served_model,
        lora_modules=args.lora_modules,
        request_logger=None,
        chat_template=args.chat_template
    )
    # openai_serving_completion = This is disabled since it is not used in the current implementation
