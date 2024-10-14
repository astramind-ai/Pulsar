import json
from typing import Optional

from huggingface_hub import hf_hub_download
from huggingface_hub.utils import EntryNotFoundError
from transformers import AutoConfig, AutoTokenizer

from app.utils.models.list_model import fix_model_name, check_if_path_is_in_hf_format


async def maybe_get_chat_template(path: str) -> Optional[str]:
    """Try to infer the chat template from a given model path."""
    # Try to get the chat template from the tokenizer class
    if not await check_if_path_is_in_hf_format(path):
        # we fix the path name
        path = await fix_model_name(path.split('/')[-1])
    try:
        if template:= AutoTokenizer.from_pretrained(path).chat_template:
            # we return the template if it exists
            return template
        config = AutoConfig.from_pretrained(path)
    except ValueError as e:
        if 'model_type' in str(e):
            # if the conf file is not found, we try to download the config file of an adapter
            try:
                config_path = hf_hub_download(path, 'adapter_config.json')  # We try to first download the config file of an adapter
            except EntryNotFoundError:
                config_path = hf_hub_download(path, 'config.json')
            config = json.loads(open(config_path).read())
        else:
            # if the config file is not found, we return None
            return None

    if isinstance(config, dict) and 'base_model_name_or_path' in config:
        template = AutoTokenizer.from_pretrained(config['base_model_name_or_path']).chat_template
        if template:
            return template

        old_model_name = config['base_model_name_or_path']
        config = json.loads(open(hf_hub_download(config['base_model_name_or_path'], 'config.json')).read())

        while '_name_or_path' in config and old_model_name != config['_name_or_path']:
            # We try to recursively find the chat template
            template = AutoTokenizer.from_pretrained(config['_name_or_path']).chat_template
            if template:
                return template
            config = json.loads(open(hf_hub_download(config['_name_or_path'], 'config.json')).read())
            old_model_name = config['_name_or_path']

    return None

