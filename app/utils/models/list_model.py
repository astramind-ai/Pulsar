import asyncio
import json
import os

from app.utils.definitions import VALID_EXTENSIONS, MIN_MODEL_SIZE, MIN_LORA_SIZE, _MODELS, MODEL_PATHS, \
    SUPPORTED_VLLM_ARCHS
from app.utils.models.gguf_util import extract_gguf_info_local


async def check_if_path_is_in_hf_format(path):
    """Check if the path is in the Hugging Face format."""
    return len(path.split('/')) == 2 and not path.startswith('models--')

async def format_repo_name_to_hf(repo_name):
    """Format the repo name to the Hugging Face format."""
    return 'models--' + repo_name.replace('/', '--').replace('/', '--')


async def fix_model_name(model_name):
    """Fix the model name by removing the 'models--' prefix and replacing -- with /."""
    return model_name.replace('models--', '').replace('--', '/')


async def is_valid_model_file(file_path, is_lora):
    """Check if the file is a valid model file based on extension and size."""
    return (any(file_path.endswith(ext) for ext in VALID_EXTENSIONS) and
            await asyncio.to_thread(os.path.getsize, file_path) >= MIN_MODEL_SIZE if not is_lora else
            await asyncio.to_thread(os.path.getsize, file_path) >= MIN_LORA_SIZE)


async def check_vllm_compatibility(config_path):
    """Check if the model architecture is compatible with vllm."""
    try:
        with open(config_path, 'r') as config_file:
            config_data = json.load(config_file)
        return any(arch in _MODELS.keys() for arch in config_data.get('architectures', []))
    except (json.JSONDecodeError, IOError):
        return False


async def find_valid_model_in_snapshot(snapshot_dir, filename=None, is_lora=False):
    """Find valid model files in the snapshot directory."""
    if filename:
        file_path = os.path.join(snapshot_dir, filename)
        return file_path if await is_valid_model_file(file_path, is_lora) else None

    valid_models = []
    for file_name in await asyncio.to_thread(os.listdir, snapshot_dir):
        file_path = os.path.join(snapshot_dir, file_name)
        if await is_valid_model_file(file_path, is_lora):
            if file_path.lower().endswith('.gguf'):
                valid_models.append(file_path)
            else:
                return file_path  # Return immediately for non-gguf files

    return valid_models if valid_models else None


async def process_model_directory(model_dir, filename=None):
    """Process a model directory and return valid model paths."""
    snapshot_path = os.path.join(MODEL_PATHS, model_dir, "snapshots")
    if not os.path.exists(snapshot_path):
        return []

    for snapshot in await asyncio.to_thread(os.listdir, snapshot_path):
        snapshot_dir = os.path.join(snapshot_path, snapshot)
        valid_model = await find_valid_model_in_snapshot(snapshot_dir, filename)
        if valid_model:

            if isinstance(valid_model, list):
                # Multiple .gguf files
                gguf_metadatas = extract_gguf_info_local(valid_model[0])['metadata']
                if gguf_metadatas.get('general.architecture', None) in SUPPORTED_VLLM_ARCHS:
                    return valid_model
            elif not filename and valid_model.lower().endswith('.gguf'):
                gguf_metadatas = extract_gguf_info_local(valid_model)['metadata']
                if gguf_metadatas['general.architecture'] in SUPPORTED_VLLM_ARCHS:
                    return [valid_model]
            elif filename or await check_vllm_compatibility(os.path.join(snapshot_dir, 'config.json')):
                return [valid_model]
    return []


async def list_models_paths_in_hf_cache(model_id=None, filename=None) -> list:
    """List valid model paths in the HuggingFace cache or a specific model."""
    if model_id:
        return await process_model_directory(model_id, filename)

    models = []
    dirs = await asyncio.to_thread(os.listdir, MODEL_PATHS)
    for dir_name in dirs:
        valid_models = await process_model_directory(dir_name)
        if valid_models:
            model_name = await fix_model_name(dir_name)
            if len(valid_models) > 1:
                models.append([model_name, valid_models])
            else:
                models.append(model_name)
    return models


async def list_loras_hf(path=None):
    """List LoRA models in the HuggingFace cache."""

    async def process_lora_directory(dir_path):
        snapshot_path = os.path.join(dir_path, "snapshots")
        if not os.path.exists(snapshot_path):
            return None

        for snapshot in await asyncio.to_thread(os.listdir, snapshot_path):
            snapshot_dir = os.path.join(snapshot_path, snapshot)
            if os.path.exists(os.path.join(snapshot_dir, "adapter_config.json")):
                valid_model = await find_valid_model_in_snapshot(snapshot_dir, is_lora=True)
                if valid_model:
                    return snapshot_dir
        return None

    if path:
        return await process_lora_directory(os.path.join(MODEL_PATHS, path))

    loras = []
    dirs = await asyncio.to_thread(os.listdir, MODEL_PATHS)
    for dir_name in dirs:
        lora_dir = await process_lora_directory(os.path.join(MODEL_PATHS, dir_name))
        if lora_dir:
            loras.append(await fix_model_name(dir_name))
    return loras
