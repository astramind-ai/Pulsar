import asyncio
import json
import os
from typing import Union

import huggingface_hub
from huggingface_hub import snapshot_download, hf_hub_download
from vllm.model_executor.models import _MODELS # noqa

from app.utils.log import setup_custom_logger

logger = setup_custom_logger(__name__)


def download_model(model_name: str, file_variant=None):
    if file_variant:
        hf_hub_download(repo_id=model_name, filename=file_variant, token=os.environ.get("PULSAR_HF_TOKEN", None))
        return
    snapshot_download(repo_id=model_name, token=os.environ.get("PULSAR_HF_TOKEN", None))


async def download_and_return_dict(repo_id: str, file: str, token: str) -> Union[dict, str, None]:
    try:
        response = huggingface_hub.hf_hub_download(repo_id=repo_id, filename=file, token=token)
        if response.split(".")[-1].lower() == "json":
            with open(response, "r") as f:
                file = json.load(f)
            return file
        elif response.split(".")[-1].lower() == "md":
            with open(response, "r") as f:
                file = f.read()
            return file
    except Exception:
        return None


async def check_file_in_huggingface_repo(user_repo_id,
                                         filename="adapter_config.json",
                                         model_token=os.environ.get("PULSAR_HF_TOKEN", None)):
    # Costruisci l'URL del file
    # file_url = f"https://huggingface.co/{user_repo_id}/resolve/main/{filename}"
    if filename == "adapter_config.json":
        logger.info(f"Checking if file {filename} exists in Hugging Face [LoRA]")

        # Esegui la richiesta GET
        response = await download_and_return_dict(repo_id=user_repo_id, file=filename, token=model_token)

        # Controlla se il file esiste
        if response:
            logger.info(f"File {filename} found in Hugging Face repo {user_repo_id}.")
            try:

                model_base = response.get('base_model_name_or_path', None)
                if model_base is None:
                    model_base = response['model_name']
                model_config = await download_and_return_dict(repo_id=model_base, file="config.json", token=model_token)
                if model_config['architectures'][0] not in _MODELS.keys():
                    logger.error(f"Model {user_repo_id} is either not a CausalLM model or it not suppoerted by vllm.")
                    return False

            except Exception as e:
                logger.debug("Wrong base model name, retrying...")  # the config probably have a wrong base model name
                try:
                    model_config = await download_and_return_dict(repo_id=user_repo_id, file="README.md",
                                                                  token=model_token)
                    model_name = model_config.split("base_model: ")[1].split("\n")[0]  # get the correct name
                    model_config = await download_and_return_dict(repo_id=model_name, file="config.json",
                                                                  token=model_token)

                    if model_config['architectures'][0] not in _MODELS.keys():
                        logger.error(
                            f"Model {user_repo_id} is either not a CausalLM model or it not suppoerted by vllm.")
                        return False
                    else:
                        return (
                            f"{model_config.get('hidden_size', model_config.get('n_embed', model_config.get('n_embd', model_config.get('d_model', 0))))},"
                            f"{model_config.get('intermediate_size', model_config.get('n_inner', 0))},"
                            f"{model_config.get('model_type', None)},"
                            f"{model_config.get('num_attention_heads', model_config.get('n_head', model_config.get('n_heads', 0)))},"
                            f"{model_config.get('num_hidden_layers', model_config.get('n_layer', model_config.get('n_layers', 0)))},"
                            f"{model_config['architectures'][0]}")
                except Exception as e:

                    logger.error(f"Error {e} parsing {filename} in Hugging Face repo {user_repo_id}.")
                    return False
            return (
                f"{model_config.get('hidden_size', model_config.get('n_embed', model_config.get('n_embd', model_config.get('d_model', 0))))},"
                f"{model_config.get('intermediate_size', model_config.get('n_inner', 0))},"
                f"{model_config.get('model_type', None)},"
                f"{model_config.get('num_attention_heads', model_config.get('n_head', model_config.get('n_heads', 0)))},"
                f"{model_config.get('num_hidden_layers', model_config.get('n_layer', model_config.get('n_layers', 0)))},"
                f"{model_config['architectures'][0]}")
        else:
            logger.info(f"File {filename} not found in Hugging Face repo {user_repo_id}.")
            return False
    elif filename == "config.json":
        logger.info(f"Checking if file {filename} exists in Hugging Face [Model]")
        model_config = await download_and_return_dict(repo_id=user_repo_id, file="config.json",
                                                      token=model_token)
        if model_config:
            model_arch = model_config.get('architectures', None)
            if model_arch is None:
                return False
            if model_arch[0] not in _MODELS.keys():
                logger.error(
                    f"Model {user_repo_id} is either not a CausalLM model or it not suppoerted by vllm.")
                return False
            else:
                return (
                    f"{model_config.get('hidden_size', model_config.get('n_embed', model_config.get('n_embd', model_config.get('d_model', 0))))},"
                    f"{model_config.get('intermediate_size', model_config.get('n_inner', 0))},"
                    f"{model_config.get('model_type', None)},"
                    f"{model_config.get('num_attention_heads', model_config.get('n_head', model_config.get('n_heads', 0)))},"
                    f"{model_config.get('num_hidden_layers', model_config.get('n_layer', model_config.get('n_layers', 0)))},"
                    f"{model_config['architectures'][0]}")

        else:
            logger.info(f"File {filename} not found in Hugging Face repo {user_repo_id}.")
            return False


async def download_model_async(ml_model_name, file_variant=None):
    """
    Asynchronously download a model without blocking the event loop.
    :param ml_model_name:
    :param file_variant:
    :return:
    """

    def blocking_download():
        # Assuming download_model is a synchronous function that downloads a model
        download_model(ml_model_name, file_variant)
        return

    logger.info(f"Downloading model {ml_model_name}")
    # Run the blocking function in a separate thread
    model_name = await asyncio.to_thread(blocking_download)
    return model_name
