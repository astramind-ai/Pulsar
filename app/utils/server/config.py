from transformers.testing_utils import get_gpu_count
import os
import yaml
from app.utils.memory.cuda_mem import  get_free_cuda_memory

template = {
    "host": '0.0.0.0',
    "port": 40000,
    "uvicorn_log_level": "info",
    "allow_credentials": False,
    "allowed_origins": ["*"],
    "allowed_methods": ["*"],
    "allowed_headers": ["*"],
    "trust_remote_code": True,
    "tensor_parallel_size": get_gpu_count(),
    "enforce_eager": get_free_cuda_memory() < 16 * 1024 ** 3,
    "engine_use_ray": get_gpu_count() > 1,
    "auto_quantized_fallback": True,
    "quant_type_preference": "GPTQ",
    "enable_tts": False,
    "tts_model": None,
}

models = {
    "roleplay": {
        "18+": {
            "ArliAI/Llama-3.1-70B-ArliAI-RPMax-v1.1-GPTQ_Q4": 40,
            "ArliAI/Mistral-Small-22B-ArliAI-RPMax-v1.1-GPTQ_Q8": 23,
            "ArliAI/Mistral-Small-22B-ArliAI-RPMax-v1.1-GPTQ_Q4":12.2,
            "AmmarByFar/MN-12B-Celeste-V1.9-AWQ-4bit": 8.3,
            "TheBloke/LLaMA2-13B-Estopia-GPTQ": 7.3,
            "PrunaAI/TheDrummer-Llama-3SOME-8B-v1-bnb-4bit-smashed": 6,
            "PrunaAI/TheDrummer-Gemmasutra-9B-v1-bnb-4bit-smashed": 6.5,
            "hugging-quants/Meta-Llama-3.1-8B-Instruct-GPTQ-INT4": 5, #Added even if ti is not 18+ because for that low of a vram it is a good choice
            "AMead10/Llama-3.2-3B-Instruct-AWQ": 3, # same
            "ciCic/llama-3.2-1B-Instruct-AWQ": 1.6, # same
        },
        "all-ages": {
            "ArliAI/Llama-3.1-70B-ArliAI-RPMax-v1.1-GPTQ_Q4": 40,
            "ArliAI/Mistral-Small-22B-ArliAI-RPMax-v1.1-GPTQ_Q8": 23,
            "ArliAI/Mistral-Small-22B-ArliAI-RPMax-v1.1-GPTQ_Q4": 12.2,
            "casperhansen/mistral-nemo-instruct-2407-awq": 8,
            "solidrust/Mistral-NeMo-Minitron-8B-Base-AWQ": 6,
            "solidrust/L3-8B-Stheno-v3.2-AWQ": 6.2,
            "hugging-quants/Meta-Llama-3.1-8B-Instruct-GPTQ-INT4": 5, # same
            "AMead10/Llama-3.2-3B-Instruct-AWQ": 3, # same
            "ciCic/llama-3.2-1B-Instruct-AWQ": 1.6, # same
        }
    },
    "general": {
        "all-ages": {
            "hugging-quants/Meta-Llama-3.1-70B-Instruct-AWQ-INT4": 40,
            "nvidia/Mistral-NeMo-Minitron-8B-Instruct": 15,
            "shuyuej/Mistral-Nemo-Instruct-2407-GPTQ-INT8": 13,
            "AMead10/Mistral-Small-Instruct-2409-awq": 12,
            "iqbalamo93/Meta-Llama-3.1-8B-Instruct-GPTQ-Q_8": 9.3,
            "shuyuej/Mistral-Nemo-Instruct-2407-GPTQ": 8.5,
            "hugging-quants/Meta-Llama-3.1-8B-Instruct-GPTQ-INT4": 5,
            "AMead10/Llama-3.2-3B-Instruct-AWQ": 3,
            "ciCic/llama-3.2-1B-Instruct-AWQ": 1.6,
        }
    }
}


def get_model_choice():
    use_type = os.environ.get('PRIMARY_USE', "general")
    is_adult_content = os.environ.get('IS_ADULT_CONTENT', "False") == 'True'
    available_memory = get_free_cuda_memory()

    content_type = "18+" if is_adult_content and use_type=='roleplay' else "all-ages"

    if use_type not in models or content_type not in models[use_type]:
        raise ValueError(f"Invalid use type or content type: {use_type}, {content_type}")

    suitable_models = models[use_type][content_type]

    for model, required_memory in sorted(suitable_models.items(), key=lambda x: x[1], reverse=True):
        if available_memory >= (
        required_memory * 1024 ** 3 * 1.5 if required_memory < 12 else required_memory * 1024 ** 3 + 4096):  # we multiply by 1024**3 to convert from GB to bytes and times 1.5 to leave space for KV Cache
            return model

    raise ValueError("No suitable model found for the available memory, try closing some applications that are using gpu memory")


def generate_yaml_entry(path):
    config = template.copy()
    chosen_model = get_model_choice()
    config['model'] = chosen_model
    config['tokenizer'] = chosen_model


    #save the config to a yaml file
    with open(path, 'w') as file:
        yaml.dump(config, file)
