from __future__ import annotations

from ..llm_client import call_structured
from ..prompts.loader import load_prompt, render_style_guide
from ..state import DraftContent, FactSheet, ReviewReport, StyleGuide
from ..validators import structural_issues

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "pass": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["pass", "issues"],
}


def run(
    draft: DraftContent,
    fact_sheet: FactSheet,
    style_guide: StyleGuide,
    target_format: str,
) -> tuple[ReviewReport, DraftContent]:
    system = load_prompt("editor") + "\n\n" + render_style_guide(style_guide)
    claims_text = "\n".join(f"- ({c.confidence}) {c.claim}" for c in fact_sheet.claims)
    draft_text = draft.body_md or "\n".join(f"[슬라이드{s.order}] {s.text}" for s in draft.slides)
    user_content = (
        f"target_format: {target_format}\n\n"
        f"검증된 사실 목록:\n{claims_text}\n\n"
        f"제목: {draft.title}\n\n본문:\n{draft_text}"
    )

    result = call_structured(
        system=system,
        user_content=user_content,
        tool_name="submit_review",
        tool_description="글 검수 결과를 제출한다",
        input_schema=TOOL_SCHEMA,
    )

    # LLM 판단(문법/톤/사실관계) + 코드 기반 결정론적 검증(슬라이드 수/글자수)을 합친다.
    # 구조적 기준을 LLM이 놓치거나 잘못 세더라도 여기서 무조건 잡아낸다.
    issues = list(result["issues"])
    struct_issues = structural_issues(draft, style_guide, target_format)
    issues.extend(struct_issues)
    passed = bool(result["pass"]) and not struct_issues

    review_report = ReviewReport(**{"pass": passed}, issues=issues)
    return review_report, draft
