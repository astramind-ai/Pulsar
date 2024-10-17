import os
import uuid
from pathlib import Path

from dotenv import set_key, load_dotenv
from vllm.model_executor.models import _MODELS  # noqa

from app.utils.models.model_paths import get_model_path

load_dotenv()

SERVER_URL = "https://pulsar.astramind.ai"

# DB related
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days
UPLOAD_DIRECTORY = os.path.join(".", "static", "item_images")
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)
LOCAL_TOKEN = uuid.uuid4().hex
SECRET_KEY = os.environ.get("SECRET_KEY", None)
if not SECRET_KEY:
    SECRET_KEY = ''.join([str(uuid.uuid4()) for _ in range(3)])
    os.environ['SECRET_KEY'] = SECRET_KEY
    set_key('.env', 'SECRET_KEY', SECRET_KEY)

DATABASE_URL = (
    f"postgresql+asyncpg://"
    f"{os.environ.get('PULSAR_DB_USER', 'astramind')}:"
    f"{os.environ.get('PULSAR_DB_PASSWORD')}@"
    f"{os.environ.get('PULSAR_DB_NAME', 'localhost/pulsar')}"
)

# Image related constants
ALLOWED_EXTENSIONS = [
    'jpg', 'jpeg', 'png', 'gif', 'bmp',
    'webp', 'svg', 'tiff', 'ico', 'heic',
]
ABSOLUTE_UPLOAD_DIRECTORY = Path(UPLOAD_DIRECTORY).resolve()
MAX_SIZE = (1024, 1024)

# Model related
VALID_EXTENSIONS = ('.pt', '.ckpt', '.safetensors', '.bin', '.pth', '.gguf')
MIN_MODEL_SIZE = 250 * 1024 * 1024  # 250 MB in bytes
MIN_LORA_SIZE = 10 * 1024 * 1024  # 10 MB in bytes
SUPPORTED_VLLM_ARCHS = {elem for pair in _MODELS.values() for elem in pair}
MODEL_PATHS = get_model_path()

# Personality related
PERSONALITY_REGEX_SCHEMAS = {
    "name": ("regex", "Write only the character's name, keeping it short and memorable", ".{1,50}"),
    "sexuality": ("choice", "Choose the character's sexuality from the list",
                  ["heterosexual", "homosexual", "bisexual", "asexual", "pansexual", "other"]),
    "gender": ("choice", "Choose the character's gender from the list", ["male", "female", "non-binary", "other"]),
    "species": ("regex", "Write the character species or type", ".{1,50}"),
    "history": ("regex",
                "Summarize the character's life story and key events in 2-3 short sentences. Exclude physical descriptions.",
                ".{100,500}"),
    "description": ("regex",
                    "Write a brief, enticing, and playful character description in 2-3 sentences to attract users. Focus on personality and unique traits.",
                    ".{100,500}"),
    "appearance": ("regex",
                   "Describe the character's appearance, clothing, and accessories in 2-3 concise sentences.",
                   ".{100,500}"),
    "personality": ("regex",
                    "Summarize the character's personality and temperament in 2-3 short, impactful sentences.",
                    ".{100,500}"),
    "abilities": ("regex",
                  "List 1 to 5 of the character's main abilities or skills. Format: [\"skill1\",\"skill2\"]",
                  r'\[(?:"[^"]{1,30}"(?:,\s*"[^"]{1,30}"){0,4})\]'),
    "allies": ("regex",
               "List 0 to 3 of the character's key allies. Format: [\"name1\",\"name2\"]",
               r'\[(?:"[^"]{1,30}"(?:,\s*"[^"]{1,30}"){0,2})?\]'),
    "enemies": ("regex",
                "List 0 to 3 of the character's main adversaries. Format: [\"name1\",\"name2\"]",
                r'\[(?:"[^"]{1,30}"(?:,\s*"[^"]{1,30}"){0,2})?\]'),
}

# Chat related
ALLOWED_MESSAGE_FIELDS = {'id', 'content', 'role', 'version', 'parent_message_id'}
SUMMARIZATION_TEMPLATE = """I want you to summarize this text in a way that I will be able to remember the following chat 
topics based on this, {first_user_message}. Now summarize it in five word maxiumum, with no bullet points:"""

# Tunnel related
TUNNEL_TYPES = ["localtunnel", "ngrok"]  # TODO: add sish, "serveo"

# GGUF related
GGUF_MAGIC = b"GGUF"
INITIAL_CHUNK_SIZE = 8_000_000  # 8 MB

# Server related
# Configuration
GITHUB_REPO = "astramind-ai/Pulsar"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CONF_FILE = "last.yml"