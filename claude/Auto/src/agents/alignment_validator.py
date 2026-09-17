from __future__ import annotations

import base64
from pathlib import Path

from ..llm_client import call_structured_with_images
from ..prompts.loader import load_prompt, render_style_guide
from ..state import AlignmentReport, DraftContent, ImageItem, StyleGuide

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "pass": {"type": "boolean"},
        "mismatches": {"type": "array", "items": {"type": "string"}},
        "fault": {"type": ["string", "null"], "enum": ["text", "image", None]},
    },
    "required": ["pass", "mismatches"],
}


def run(
    reviewed_content: DraftContent,
    image_set: list[ImageItem],
    style_guide: StyleGuide,
) -> AlignmentReport:
    system = load_prompt("alignment_validator") + "\n\n" + render_style_guide(style_guide)

    text_parts = [f"제목: {reviewed_content.title}"]
    if reviewed_content.slides:
        for s in reviewed_content.slides:
            text_parts.append(f"[슬라이드 {s.order}] {s.text}")
    else:
        text_parts.append(reviewed_content.body_md or "")
    user_text = "\n".join(text_parts)

    images_b64: list[tuple[str, str]] = []
    for img in image_set:
        data = Path(img.path).read_bytes()
        images_b64.append((img.section_id, base64.b64encode(data).decode("utf-8")))

    result = call_structured_with_images(
        system=system,
        user_text=user_text,
        images=images_b64,
        tool_name="submit_alignment",
        tool_description="글과 이미지의 정합성 검증 결과를 제출한다",
        input_schema=TOOL_SCHEMA,
    )
    return AlignmentReport(
        **{"pass": result["pass"]},
        mismatches=result.get("mismatches", []),
        fault=result.get("fault"),
    )
