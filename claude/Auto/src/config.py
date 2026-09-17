import os
from pathlib import Path

from dotenv import load_dotenv

AUTO_ROOT = Path(__file__).resolve().parent.parent
API_KEYS_FILE = AUTO_ROOT / "api_keys.txt"

if API_KEYS_FILE.exists():
    load_dotenv(dotenv_path=API_KEYS_FILE)
else:
    raise RuntimeError(
        f"{API_KEYS_FILE} 파일이 없습니다. "
        f"{AUTO_ROOT / 'api_keys.example.txt'} 를 복사해 api_keys.txt로 저장하고 값을 채워주세요."
    )

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")

MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "2"))

OUTPUT_DIR = AUTO_ROOT / "output"

WORDPRESS_URL = os.environ.get("WORDPRESS_URL")
WORDPRESS_USER = os.environ.get("WORDPRESS_USER")
WORDPRESS_APP_PASSWORD = os.environ.get("WORDPRESS_APP_PASSWORD")

IG_BUSINESS_ACCOUNT_ID = os.environ.get("IG_BUSINESS_ACCOUNT_ID")
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN")
