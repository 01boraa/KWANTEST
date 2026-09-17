from __future__ import annotations

from pathlib import Path

from ..image_client import generate_image
from ..llm_client import call_structured
from ..prompts.loader import load_prompt, render_style_guide
from ..state import DraftContent, ImageItem, StyleGuide

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "images": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section_id": {"type": "string"},
                    "prompt": {"type": "string"},
                    "alt_text": {"type": "string"},
                },
                "required": ["section_id", "prompt", "alt_text"],
            },
        }
    },
    "required": ["images"],
}


def run(
    reviewed_content: DraftContent,
    style_guide: StyleGuide,
    target_format: str,
    out_dir: Path,
    feedback: str | None = None,
) -> list[ImageItem]:
    system = load_prompt("image_generator") + "\n\n" + render_style_guide(style_guide)
    if target_format == "card_news":
        sections_text = "\n".join(f"[slide-{s.order}] {s.text}" for s in reviewed_content.slides)
    else:
        sections_text = f"[cover] {reviewed_content.title}\n{reviewed_content.body_md}"
    user_content = f"target_format: {target_format}\n\n{sections_text}"
    if feedback:
        user_content += f"\n\n[이전 반려 사유 - 프롬프트에 반영할 것]\n{feedback}"

    result = call_structured(
        system=system,
        user_content=user_content,
        tool_name="submit_image_prompts",
        tool_description="섹션별 이미지 생성 프롬프트를 제출한다",
        input_schema=TOOL_SCHEMA,
    )

    images: list[ImageItem] = []
    for item in result["images"]:
        out_path = out_dir / f"{item['section_id']}.png"
        generate_image(item["prompt"], out_path)
        images.append(
            ImageItem(
                section_id=item["section_id"],
                path=str(out_path),
                prompt=item["prompt"],
                alt_text=item["alt_text"],
            )
        )
    return images
