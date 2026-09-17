from __future__ import annotations

from ..llm_client import call_structured
from ..prompts.loader import load_prompt
from ..state import Claim, FactSheet, RejectedSource, SourceItem, VerifyReport

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["claim", "sources", "confidence"],
            },
        },
        "rejected_sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["url", "reason"],
            },
        },
        "pass": {"type": "boolean"},
        "reason": {"type": "string"},
        "feedback_for_collector": {"type": ["string", "null"]},
    },
    "required": ["claims", "rejected_sources", "pass", "reason"],
}


def run(topic: str, raw_sources: list[SourceItem]) -> tuple[FactSheet, VerifyReport]:
    system = load_prompt("verifier")
    sources_text = "\n\n".join(
        f"[{i + 1}] {s.title}\nURL: {s.url}\n{s.raw_text[:2000]}"
        for i, s in enumerate(raw_sources)
    )
    user_content = f"주제: {topic}\n\n수집된 자료:\n{sources_text}"

    result = call_structured(
        system=system,
        user_content=user_content,
        tool_name="submit_verification",
        tool_description="자료 검증 결과를 제출한다",
        input_schema=TOOL_SCHEMA,
    )

    fact_sheet = FactSheet(
        claims=[Claim(**c) for c in result["claims"]],
        rejected_sources=[RejectedSource(**r) for r in result["rejected_sources"]],
    )
    verify_report = VerifyReport(
        **{"pass": result["pass"]},
        reason=result["reason"],
        feedback_for_collector=result.get("feedback_for_collector"),
    )
    return fact_sheet, verify_report
