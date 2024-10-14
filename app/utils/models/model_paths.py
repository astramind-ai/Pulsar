import os
import sys


def get_model_path():
    """Determine the model path based on the operating system."""
    if sys.platform.startswith('win'):
        return os.path.join(os.environ.get('APPDATA', 'C:\\'), 'huggingface', 'hub')
    elif sys.platform.startswith('darwin'):
        return os.path.expanduser('~/Library/Caches/huggingface/hub')
    else:
        return os.path.expanduser(os.path.join(os.environ.get("XDG_CACHE_HOME", "~/.cache"), 'huggingface', 'hub'))


async def get_hf_path(
        model_name: str,
) -> str:
    return "models--" + model_name.replace("/", "--")