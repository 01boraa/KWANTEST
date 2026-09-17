"""
실제 API 호출 없이(mock으로 LLM/이미지 생성 대체) pipeline.py의 제어 흐름
(재시도 카운팅, 반려 라우팅, 재시도 한도 초과 시 사람 검토 전환)이 설계대로
동작하는지 검증하는 스모크 테스트.

실행: cd claude/Auto && source .venv/bin/activate && python -m tests.test_pipeline_mock
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.pipeline import HumanReviewNeeded, run_pipeline
from src.state import (
    AlignmentReport,
    Claim,
    DraftContent,
    FactSheet,
    FinalApproval,
    ImageItem,
    PublishResult,
    ReviewReport,
    Slide,
    SourceItem,
    StyleGuide,
    VerifyReport,
)

STYLE = StyleGuide(card_news_slide_count=3, max_slide_chars=60, blog_target_chars=200)


def make_sources() -> list[SourceItem]:
    return [
        SourceItem(url="https://example.com/1", title="t1", snippet="s1", raw_text="r1", fetched_at="now")
    ]


def make_fact_sheet() -> FactSheet:
    return FactSheet(claims=[Claim(claim="테스트 주장", sources=["https://example.com/1"], confidence="high")])


def make_blog_draft(ok: bool = True) -> DraftContent:
    body = "가" * (200 if ok else 20)  # ok=False -> 글자수 목표(200) 크게 미달 -> 구조 검증 fail 유도
    return DraftContent(
        title="테스트 제목",
        body_md=body,
        meta_description="메타 설명",
        hashtags=["#test"],
    )


def make_images(n: int) -> list[ImageItem]:
    return [
        ImageItem(section_id=f"slide-{i+1}" if n > 1 else "cover", path=f"/tmp/fake-{i}.png", prompt="p", alt_text="a")
        for i in range(n)
    ]


def fake_generate_image(prompt, out_path: Path, size="1024x1024"):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)  # 최소한의 PNG 헤더 + 더미 바이트
    return out_path


def test_happy_path():
    with patch("src.agents.collector.run", return_value=make_sources()), patch(
        "src.agents.verifier.run", return_value=(make_fact_sheet(), VerifyReport(**{"pass": True}, reason="ok"))
    ), patch("src.agents.writer.run", return_value=make_blog_draft(ok=True)), patch(
        "src.agents.editor.run",
        return_value=(ReviewReport(**{"pass": True}, issues=[]), make_blog_draft(ok=True)),
    ), patch("src.agents.image_generator.generate_image", side_effect=fake_generate_image), patch(
        "src.agents.image_generator.call_structured",
        return_value={"images": [{"section_id": "cover", "prompt": "p", "alt_text": "a"}]},
    ), patch(
        "src.agents.alignment_validator.run",
        return_value=AlignmentReport(**{"pass": True}, mismatches=[], fault=None),
    ), patch(
        "src.agents.supervisor.run",
        return_value=FinalApproval(approved=True, failed_checks=[], fault_stage=None, notes="ok"),
    ), patch(
        "src.agents.publisher.run",
        return_value=PublishResult(platform="wordpress", post_id="1", url="https://x", status="draft_created"),
    ):
        state = run_pipeline("테스트 주제", "blog", STYLE, max_retries=2, interactive=False)

    assert state.publish_result is not None
    assert state.retry_counts == {}
    print("test_happy_path: OK")


def test_verify_retry_then_pass():
    calls = {"n": 0}

    def verifier_side_effect(topic, raw_sources):
        calls["n"] += 1
        if calls["n"] == 1:
            return make_fact_sheet(), VerifyReport(**{"pass": False}, reason="fail", feedback_for_collector="다시")
        return make_fact_sheet(), VerifyReport(**{"pass": True}, reason="ok")

    with patch("src.agents.collector.run", return_value=make_sources()) as collector_mock, patch(
        "src.agents.verifier.run", side_effect=verifier_side_effect
    ), patch("src.agents.writer.run", return_value=make_blog_draft(ok=True)), patch(
        "src.agents.editor.run",
        return_value=(ReviewReport(**{"pass": True}, issues=[]), make_blog_draft(ok=True)),
    ), patch("src.agents.image_generator.generate_image", side_effect=fake_generate_image), patch(
        "src.agents.image_generator.call_structured",
        return_value={"images": [{"section_id": "cover", "prompt": "p", "alt_text": "a"}]},
    ), patch(
        "src.agents.alignment_validator.run",
        return_value=AlignmentReport(**{"pass": True}, mismatches=[], fault=None),
    ), patch(
        "src.agents.supervisor.run",
        return_value=FinalApproval(approved=True, failed_checks=[], fault_stage=None, notes="ok"),
    ), patch(
        "src.agents.publisher.run",
        return_value=PublishResult(platform="wordpress", post_id="1", url="https://x", status="draft_created"),
    ):
        state = run_pipeline("테스트 주제", "blog", STYLE, max_retries=2, interactive=False)

    assert collector_mock.call_count == 2
    assert state.retry_counts["collect"] == 1
    print("test_verify_retry_then_pass: OK")


def test_verify_exhausts_retries_triggers_human_review():
    with patch("src.agents.collector.run", return_value=make_sources()) as collector_mock, patch(
        "src.agents.verifier.run",
        return_value=(make_fact_sheet(), VerifyReport(**{"pass": False}, reason="fail", feedback_for_collector="다시")),
    ):
        try:
            run_pipeline("테스트 주제", "blog", STYLE, max_retries=1, interactive=False)
            raise AssertionError("HumanReviewNeeded가 발생했어야 합니다")
        except HumanReviewNeeded as e:
            assert e.stage == "collect"

    assert collector_mock.call_count == 2  # max_retries=1 -> 2번째 실패에서 중단
    print("test_verify_exhausts_retries_triggers_human_review: OK")


def test_alignment_fault_text_reroutes_to_writer_editor():
    align_calls = {"n": 0}

    def alignment_side_effect(content, images, style_guide):
        align_calls["n"] += 1
        if align_calls["n"] == 1:
            return AlignmentReport(**{"pass": False}, mismatches=["텍스트가 이미지와 안 맞음"], fault="text")
        return AlignmentReport(**{"pass": True}, mismatches=[], fault=None)

    writer_calls = {"n": 0}

    def writer_side_effect(fact_sheet, style_guide, target_format, feedback=None):
        writer_calls["n"] += 1
        return make_blog_draft(ok=True)

    with patch("src.agents.collector.run", return_value=make_sources()), patch(
        "src.agents.verifier.run", return_value=(make_fact_sheet(), VerifyReport(**{"pass": True}, reason="ok"))
    ), patch("src.agents.writer.run", side_effect=writer_side_effect), patch(
        "src.agents.editor.run",
        return_value=(ReviewReport(**{"pass": True}, issues=[]), make_blog_draft(ok=True)),
    ), patch("src.agents.image_generator.generate_image", side_effect=fake_generate_image), patch(
        "src.agents.image_generator.call_structured",
        return_value={"images": [{"section_id": "cover", "prompt": "p", "alt_text": "a"}]},
    ), patch("src.agents.alignment_validator.run", side_effect=alignment_side_effect), patch(
        "src.agents.supervisor.run",
        return_value=FinalApproval(approved=True, failed_checks=[], fault_stage=None, notes="ok"),
    ), patch(
        "src.agents.publisher.run",
        return_value=PublishResult(platform="wordpress", post_id="1", url="https://x", status="draft_created"),
    ):
        state = run_pipeline("테스트 주제", "blog", STYLE, max_retries=2, interactive=False)

    assert writer_calls["n"] == 2  # 최초 1회 + fault=text로 인한 재작성 1회
    assert align_calls["n"] == 2
    assert state.retry_counts["align_text"] == 1
    print("test_alignment_fault_text_reroutes_to_writer_editor: OK")


def test_editor_structural_check_forces_fail():
    """editor.py의 결정론적 구조 검증: LLM이 pass=True라고 해도 슬라이드 수가
    style_guide와 다르면 무조건 반려되어야 한다."""
    from src.agents import editor
    from src.state import FactSheet as FS

    wrong_slide_count_draft = DraftContent(
        title="t",
        slides=[Slide(order=1, text="a", image_prompt="p")],  # style_guide는 3장을 요구
    )

    with patch(
        "src.agents.editor.call_structured",
        return_value={"pass": True, "issues": []},  # LLM은 통과라고 판단
    ):
        review_report, _ = editor.run(wrong_slide_count_draft, FS(), STYLE, "card_news")

    assert review_report.pass_ is False
    assert any("슬라이드" in issue for issue in review_report.issues)
    print("test_editor_structural_check_forces_fail: OK")


if __name__ == "__main__":
    test_happy_path()
    test_verify_retry_then_pass()
    test_verify_exhausts_retries_triggers_human_review()
    test_alignment_fault_text_reroutes_to_writer_editor()
    test_editor_structural_check_forces_fail()
    print("\n모든 파이프라인 제어 흐름 테스트 통과")
