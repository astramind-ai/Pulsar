import dataclasses
import os
import warnings
from dataclasses import dataclass
from dataclasses import field
from typing import List, Optional, Dict

import torch.cuda
import yaml
from vllm import AsyncEngineArgs

from app.utils.log import setup_custom_logger
from app.utils.memory.cuda_mem import get_total_cuda_memory, get_used_cuda_memory

logger = setup_custom_logger(__name__)


def astra_parser_wrapper(parser):
    """
    Wrap a parser to add arguments
    :param parser:
    :return:
    """
    parser.description = "vLLM Based OpenAI-Compatible RESTful API server By AstraMind AI"
    parser.add_argument("--auto-quantized-fallback", type=bool, default=True,
                        help="Automatically pick a quantized model if the model is too big")
    parser.add_argument("--quant-type-preference", type=str, default="GPTQ",
                        help="The preference for quantization types, either GPTQ or AWQ")
    parser.add_argument("--use-config-file", type=bool, default=True, help="Whether to use a server config file")
    parser.add_argument("--server-config-file", type=str, default="last.yml",
                        help="The path to the server configuration file")
    parser.add_argument("--enable-tts", type=bool, default=False, help="Whether to enable TTS")
    parser.add_argument("--enable-txt2img", type=bool, default=False, help="Whether to enable txt2img")
    return parser


@dataclass
class ExtendedAsyncEngineArgs(AsyncEngineArgs):
    auto_quantized_fallback: bool = True
    quant_type_preference: str = "GPTQ"
    enable_tts: bool = False
    enable_txt2img: bool = False
    use_config_file: bool = True
    server_config_file: str = "last.yml"

    @classmethod
    def from_model_conf(cls, config: dict):
        field_names = {field.name for field in dataclasses.fields(cls)}
        filtered_config = {k: v for k, v in config.items() if k in field_names}
        eng_args = cls(**filtered_config)
        eng_args.set_smart_gpu_memory_utilization()
        return eng_args

    @classmethod
    def from_yaml(cls, file: str):
        from server import CONFIG_FILE_PATH
        path = os.path.join(CONFIG_FILE_PATH, file)
        with open(path, "r") as f:
            eng_args = cls.from_model_conf(yaml.safe_load(f))
            return eng_args

    def set_smart_gpu_memory_utilization(self):
        total_memory = get_total_cuda_memory()
        used_memory = get_used_cuda_memory()
        if self.enforce_eager:
            usage_percentage = (1 - (used_memory / total_memory)) * 0.98
        else:
            # we subtract the cuda graph additional memory usage
            usage_percentage = ((1 - (used_memory / total_memory)) - (2.5 / (total_memory / 1024**3))) * 0.98

        # TODO: Define actual whisper / tts memory usage based on the fixed execution load and the available memory
        #whisper_memory_usage = 0.1 if self.enable_tts else 0
        # TODO: Define actual txt2img memory usage
        #txt2img_memory_usage = 0.15 if self.enable_txt2img else 0
        #usage_percentage -= whisper_memory_usage + txt2img_memory_usage
        self.gpu_memory_utilization = usage_percentage


    def save_to_yaml(self):
        from server import CONFIG_FILE_PATH
        path = os.path.join(CONFIG_FILE_PATH, "last.yml")
        with open(path, "w") as f:
            yaml.dump(dataclasses.asdict(self), f)


@dataclass
class ExtendedAsyncCompleteServerArgs(ExtendedAsyncEngineArgs):
    host: Optional[str] = '127.0.0.1'
    port: int = 40000
    uvicorn_log_level: str = 'info'
    allow_credentials: bool = False
    allowed_origins: List[str] = field(default_factory=lambda: ['*'])
    allowed_methods: List[str] = field(default_factory=lambda: ['*'])
    allowed_headers: List[str] = field(default_factory=lambda: ['*'])
    api_key: Optional[str] = None
    lora_modules: Optional[Dict] = None
    chat_template: Optional[str] = None
    response_role: str = 'assistant'
    ssl_keyfile: Optional[str] = None
    ssl_certfile: Optional[str] = None
    ssl_ca_certs: Optional[str] = None
    ssl_cert_reqs: int = 0
    root_path: Optional[str] = None
    middleware: List = field(default_factory=list)

    use_config_file: bool = True
    server_config_file: str = "last.yml"

    kv_cache_dtype = 'fp8'

    max_lora_rank = 48
    max_loras = 4
    enable_lora = True

    tunnel_type: Optional[str] = None
    ngrok_auth_token = os.environ.get('PULSAR_NGROK_TOKEN', None)

    def get_async_eng_args(self):
        valid_fields = {f.name for f in dataclasses.fields(ExtendedAsyncEngineArgs)}
        valid_data = {k: v for k, v in dataclasses.asdict(self).items() if k in valid_fields}
        return ExtendedAsyncEngineArgs(**valid_data)

    def define_optimal_lora_config(self):
        usable_memory = get_total_cuda_memory() * self.gpu_memory_utilization
        if usable_memory <= 6 * 1000 ** 3:
            self.max_loras = 2
            self.max_lora_rank = 32
        elif usable_memory <= 12 * 1000 ** 3:
            self.max_loras = 4
            self.max_lora_rank = 32
        elif usable_memory <= 24 * 1000 ** 3:
            self.max_loras = 8
            self.max_lora_rank = 32

    def check_tunnel_config(self):
        if self.tunnel_type == 'lt':
            try:
                import py_localtunnel # noqa
            except ImportError:
                logger.error("LocalTunnel is not installed, please install it using `pip install py-localtunnel`")
                return False
        elif self.tunnel_type == 'ngrok':
            try:
                import ngrok # noqa
            except ImportError:
                logger.error("PyNgrok is not installed, please install it using `pip install ngrok`")
                return False

    def check_gpu_arch_and_set_constraints(self):
        """
        Check the GPU architecture and set constraints accordingly
        """
        if torch.cuda.is_available():
            device = torch.device("cuda")
            gpu_name = torch.cuda.get_device_name(device)
            gpu_arch = torch.cuda.get_device_capability(device)
            logger.debug(f"GPU Name: {gpu_name}, GPU Capabilities: {gpu_arch[0]}.{gpu_arch[1]}")
            if float(f"{gpu_arch[0]}.{gpu_arch[1]}") < 7:
                logger.warn("Your GPU does not support LoRA and bfloat16, they'll be disabled")
                self.dtype = "float16"
                self.kv_cache_dtype = 'auto'
                self.enable_lora = False
            elif float(f"{gpu_arch[0]}.{gpu_arch[1]}") <= 7.5:  # gpu is not capable of any dtype but fp16, lora is enabled
                self.dtype = "float16"
                self.kv_cache_dtype = 'auto'

            self.enable_lora = True
        else:
            logger.info("No GPU found, please check if this behaviour is desired")

    def __post_init__(self):
        super().__post_init__()
        self.check_gpu_arch_and_set_constraints()
        if self.enable_lora:
            self.define_optimal_lora_config()
        self.served_model_name = [self.model]
        if self.tokenizer != self.model:
            logger.warn("The chosen tokenizer is different from the model, please be sure this is intended behaviour")
        self.check_tunnel_config()
