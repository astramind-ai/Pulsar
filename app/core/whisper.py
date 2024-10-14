import torch.cuda

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

MODEL_MAPPING = {
    "4": "tiny",  # 200MB
    "5": "small"  # 500MB
}


def load_whisper(model_name: str = "distil-large-v3"):
    return WhisperModel(model_name)


def get_optimal_whisper():
    # get the available memory in gb
    available_memory = torch.cuda.memory_reserved(0) / 1024 ** 3
    # get the optimal model
    for memory, model in MODEL_MAPPING.items():
        if available_memory <= int(memory):
            return load_whisper(model)
