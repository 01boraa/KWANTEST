from __future__ import annotations

from anthropic import Anthropic

from . import config

_client: Anthropic | None = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("api_keys.txt에 ANTHROPIC_API_KEY가 설정되어 있지 않습니다.")
        _client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _extract_tool_input(response, tool_name: str) -> dict:
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input
    raise RuntimeError(f"'{tool_name}' 도구 호출 결과를 응답에서 찾지 못했습니다.")


def call_structured(
    *,
    system: str,
    user_content: str,
    tool_name: str,
    tool_description: str,
    input_schema: dict,
    model: str | None = None,
    max_tokens: int = 4096,
) -> dict:
    """LLM을 호출하고, 강제된 도구 호출(tool use)을 통해 구조화된 JSON 결과를 받는다."""
    client = get_client()
    response = client.messages.create(
        model=model or config.CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
        tools=[
            {
                "name": tool_name,
                "description": tool_description,
                "input_schema": input_schema,
            }
        ],
        tool_choice={"type": "tool", "name": tool_name},
    )
    return _extract_tool_input(response, tool_name)


def call_structured_with_images(
    *,
    system: str,
    user_text: str,
    images: list[tuple[str, str]],
    tool_name: str,
    tool_description: str,
    input_schema: dict,
    model: str | None = None,
    max_tokens: int = 4096,
) -> dict:
    """images: (라벨, base64 PNG 데이터) 목록. 이미지를 함께 첨부해 LLM을 호출한다."""
    client = get_client()
    content: list[dict] = [{"type": "text", "text": user_text}]
    for label, b64 in images:
        content.append({"type": "text", "text": f"--- 이미지: {label} ---"})
        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": b64},
            }
        )

    response = client.messages.create(
        model=model or config.CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
        tools=[
            {
                "name": tool_name,
                "description": tool_description,
                "input_schema": input_schema,
            }
        ],
        tool_choice={"type": "tool", "name": tool_name},
    )
    return _extract_tool_input(response, tool_name)
