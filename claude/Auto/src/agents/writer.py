from __future__ import annotations

from ..llm_client import call_structured
from ..prompts.loader import load_prompt, render_style_guide
from ..state import DraftContent, FactSheet, Slide, StyleGuide

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "body_md": {"type": ["string", "null"]},
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "order": {"type": "integer"},
                    "text": {"type": "string"},
                    "image_prompt": {"type": "string"},
                },
                "required": ["order", "text", "image_prompt"],
            },
        },
        "meta_description": {"type": ["string", "null"]},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "slides", "hashtags"],
}


def run(
    fact_sheet: FactSheet,
    style_guide: StyleGuide,
    target_format: str,
    feedback: str | None = None,
) -> DraftContent:
    system = load_prompt("writer") + "\n\n" + render_style_guide(style_guide)
    claims_text = "\n".join(
        f"- ({c.confidence}) {c.claim}" for c in fact_sheet.claims if c.confidence != "low"
    )
    user_content = f"target_format: {target_format}\n\n검증된 사실:\n{claims_text}"
    if feedback:
        user_content += f"\n\n[이전 반려 사유 - 반드시 반영할 것]\n{feedback}"

    result = call_structured(
        system=system,
        user_content=user_content,
        tool_name="submit_draft",
        tool_description="작성된 콘텐츠 초안을 제출한다",
        input_schema=TOOL_SCHEMA,
    )
    return DraftContent(
        title=result["title"],
        body_md=result.get("body_md"),
        slides=[Slide(**s) for s in result.get("slides", [])],
        meta_description=result.get("meta_description"),
        hashtags=result.get("hashtags", []),
    )
