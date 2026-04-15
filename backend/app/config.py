import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR", ROOT_DIR / "data")).resolve()
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
GENERATED_IMAGES_DIR = DATA_DIR / "generated-images"
BOT_CONFIG_PATH = DATA_DIR / "bot-config.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
OPENAI_IMAGE_QUALITY = os.getenv("OPENAI_IMAGE_QUALITY", "low")
OPENAI_IMAGE_FORMAT = os.getenv("OPENAI_IMAGE_FORMAT", "jpeg")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
