from __future__ import annotations

import base64
from pathlib import Path

from openai import OpenAI

from . import config

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.OPENAI_API_KEY:
            raise RuntimeError("api_keys.txt에 OPENAI_API_KEY가 설정되어 있지 않습니다.")
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def generate_image(prompt: str, out_path: Path, size: str = "1024x1024") -> Path:
    client = get_client()
    result = client.images.generate(
        model=config.OPENAI_IMAGE_MODEL,
        prompt=prompt,
        size=size,
        n=1,
    )
    image_b64 = result.data[0].b64_json
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(base64.b64decode(image_b64))
    return out_path
