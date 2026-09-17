from __future__ import annotations

from ..llm_client import call_structured
from ..prompts.loader import load_prompt, render_style_guide
from ..state import FinalApproval, PipelineState

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "failed_checks": {"type": "array", "items": {"type": "string"}},
        "fault_stage": {
            "type": ["string", "null"],
            "enum": ["writer", "editor", "image_generator", "alignment_validator", None],
        },
        "notes": {"type": "string"},
    },
    "required": ["approved", "failed_checks", "notes"],
}


def run(state: PipelineState) -> FinalApproval:
    system = load_prompt("supervisor") + "\n\n" + render_style_guide(state.style_guide)

    content = state.reviewed_content
    body = content.body_md or "\n".join(f"[슬라이드{s.order}] {s.text}" for s in content.slides)
    images_desc = "\n".join(f"- {i.section_id}: {i.alt_text}" for i in state.image_set)

    user_content = (
        f"target_format: {state.target_format}\n\n"
        f"제목: {content.title}\n본문:\n{body}\n\n"
        f"이미지 alt text 목록 ({len(state.image_set)}개):\n{images_desc}\n\n"
        f"사실검증 리포트: pass={state.verify_report.pass_}\n"
        f"글검수 리포트: pass={state.review_report.pass_}\n"
        f"조합검증 리포트: pass={state.alignment_report.pass_}"
    )

    result = call_structured(
        system=system,
        user_content=user_content,
        tool_name="submit_final_approval",
        tool_description="최종 승인 여부를 제출한다",
        input_schema=TOOL_SCHEMA,
    )
    return FinalApproval(**result)
