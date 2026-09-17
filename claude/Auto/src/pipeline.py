from __future__ import annotations

from . import config, storage
from .agents import (
    alignment_validator,
    collector,
    editor,
    image_generator,
    publisher,
    supervisor,
    verifier,
    writer,
)
from .state import PipelineState, StyleGuide


class HumanReviewNeeded(Exception):
    """자동 재시도 한도를 초과해 사람이 직접 개입해야 하는 경우."""

    def __init__(self, stage: str, reason: str, state: PipelineState):
        super().__init__(reason)
        self.stage = stage
        self.reason = reason
        self.state = state


class HumanRejected(Exception):
    """사람 검토 체크포인트에서 진행을 승인하지 않은 경우."""

    def __init__(self, stage: str, state: PipelineState):
        super().__init__(f"'{stage}' 체크포인트에서 진행이 승인되지 않았습니다.")
        self.stage = stage
        self.state = state


def _check_retry(state: PipelineState, stage: str) -> None:
    state.retry_counts[stage] = state.retry_counts.get(stage, 0) + 1
    if state.retry_counts[stage] > state.max_retries:
        state.human_review_needed = True
        state.human_review_reason = f"'{stage}' 단계 재시도 한도({state.max_retries}) 초과"
        raise HumanReviewNeeded(stage, state.human_review_reason, state)


def _human_checkpoint(stage: str, summary: str, state: PipelineState, interactive: bool) -> None:
    """
    자동화 전체를 신뢰하기보다, 리스크가 큰 두 지점에서만 사람이 최종 판단한다.
      1) 사실검증 확인 - 잘못된 사실 위에서 글/이미지가 만들어지는 것을 막는다.
      2) 최종 발행 승인 - 업로드(공개) 전 마지막 안전장치.
    interactive=False면 (예: 테스트) 체크포인트를 건너뛴다.
    """
    if not interactive:
        return
    print("\n" + "=" * 60)
    print(f"[사람 검토 체크포인트] {stage}")
    print(summary)
    print("=" * 60)
    answer = input("계속 진행할까요? [y/N]: ").strip().lower()
    if answer != "y":
        raise HumanRejected(stage, state)


def run_pipeline(
    topic: str,
    target_format: str,
    style_guide: StyleGuide,
    max_retries: int = 2,
    interactive: bool = True,
) -> PipelineState:
    state = PipelineState(
        topic=topic,
        target_format=target_format,
        style_guide=style_guide,
        max_retries=max_retries,
    )

    run_dir = storage.make_run_dir(topic, config.OUTPUT_DIR)
    images_dir = run_dir / "images"
    print(f"실행 결과 저장 위치: {run_dir}")

    # 1) A 자료수집 <-> B 자료검증
    feedback: str | None = None
    while True:
        print(f"[A] 자료수집 중... (topic={topic})")
        state.raw_sources = collector.run(topic, feedback=feedback)

        print("[B] 자료검증 중...")
        state.fact_sheet, state.verify_report = verifier.run(topic, state.raw_sources)
        if state.verify_report.pass_:
            break
        print(f"  -> 반려: {state.verify_report.reason}")
        feedback = state.verify_report.feedback_for_collector
        _check_retry(state, "collect")

    # --- 사람 체크포인트 1: 사실검증 확인 ---
    storage.save_fact_sheet(state, run_dir)
    claims_summary = "\n".join(
        f"  - ({c.confidence}) {c.claim}" for c in state.fact_sheet.claims
    )
    _human_checkpoint(
        "1. 사실검증 확인 (글쓰기 시작 전)",
        f"주제: {topic}\n검증된 주장 {len(state.fact_sheet.claims)}개:\n{claims_summary}\n\n"
        f"전체 내용: {run_dir / 'fact_sheet.json'}\n"
        f"이 사실 자료를 바탕으로 글쓰기를 진행합니다.",
        state,
        interactive,
    )

    # 2) C 글쓰기 <-> D 글검수
    feedback = None
    while True:
        print("[C] 글쓰기 중...")
        state.draft = writer.run(state.fact_sheet, state.style_guide, target_format, feedback=feedback)

        print("[D] 글 검수 중...")
        state.review_report, state.reviewed_content = editor.run(
            state.draft, state.fact_sheet, state.style_guide, target_format
        )
        if state.review_report.pass_:
            break
        print(f"  -> 반려: {state.review_report.issues}")
        feedback = "; ".join(state.review_report.issues)
        _check_retry(state, "write")

    # 3) E 이미지 생성 <-> F 조합 검증 (텍스트 문제면 C/D부터 다시)
    image_feedback: str | None = None
    while True:
        print("[E] 이미지 생성 중...")
        state.image_set = image_generator.run(
            state.reviewed_content, state.style_guide, target_format, images_dir, feedback=image_feedback
        )

        print("[F] 글+이미지 조합 검증 중...")
        state.alignment_report = alignment_validator.run(
            state.reviewed_content, state.image_set, state.style_guide
        )
        if state.alignment_report.pass_:
            break

        print(f"  -> 반려 (fault={state.alignment_report.fault}): {state.alignment_report.mismatches}")
        if state.alignment_report.fault == "image":
            image_feedback = "; ".join(state.alignment_report.mismatches)
            _check_retry(state, "image")
        else:
            _check_retry(state, "align_text")
            text_feedback = "; ".join(state.alignment_report.mismatches)
            print("  -> 텍스트 문제로 판단, C/D 재실행")
            state.draft = writer.run(
                state.fact_sheet, state.style_guide, target_format, feedback=text_feedback
            )
            state.review_report, state.reviewed_content = editor.run(
                state.draft, state.fact_sheet, state.style_guide, target_format
            )
            image_feedback = None

    # 4) G 총괄 검수
    while True:
        print("[G] 총괄 검수 중...")
        state.final_approval = supervisor.run(state)
        if state.final_approval.approved:
            break
        print(f"  -> 미승인: {state.final_approval.notes}")
        _check_retry(state, "supervise")

        fault_stage = state.final_approval.fault_stage
        if fault_stage in ("writer", "editor"):
            state.draft = writer.run(
                state.fact_sheet, state.style_guide, target_format, feedback=state.final_approval.notes
            )
            state.review_report, state.reviewed_content = editor.run(
                state.draft, state.fact_sheet, state.style_guide, target_format
            )
            state.image_set = image_generator.run(
                state.reviewed_content, state.style_guide, target_format, images_dir
            )
            state.alignment_report = alignment_validator.run(
                state.reviewed_content, state.image_set, state.style_guide
            )
        elif fault_stage in ("image_generator", "alignment_validator"):
            state.image_set = image_generator.run(
                state.reviewed_content,
                state.style_guide,
                target_format,
                images_dir,
                feedback=state.final_approval.notes,
            )
            state.alignment_report = alignment_validator.run(
                state.reviewed_content, state.image_set, state.style_guide
            )
        # fault_stage가 None이면 notes만 참고해 그대로 재검수 루프를 돈다

    # 결과물 저장 (글 + 이미지 + 미리보기 + 전체 기록)
    storage.save_content(state.reviewed_content, state.image_set, target_format, run_dir)
    preview_path = storage.save_preview_html(state.reviewed_content, state.image_set, target_format, run_dir)
    storage.save_manifest(state, run_dir)

    # --- 사람 체크포인트 2: 최종 발행 승인 ---
    if target_format == "card_news":
        size_desc = f"슬라이드 {len(state.reviewed_content.slides)}장"
    else:
        body = state.reviewed_content.body_md or ""
        size_desc = f"{len(body.replace(' ', '').replace(chr(10), ''))}자"
    _human_checkpoint(
        "2. 최종 발행 승인 (업로드 직전)",
        f"제목: {state.reviewed_content.title}\n형식: {target_format} ({size_desc})\n"
        f"이미지: {len(state.image_set)}개\n"
        f"미리보기(브라우저로 열어서 확인): {preview_path}\n"
        f"저장 위치: {run_dir}",
        state,
        interactive,
    )

    # 5) H 업로드
    print("[H] 업로드 중...")
    state.publish_result = publisher.run(state.reviewed_content, state.image_set, target_format)
    storage.save_manifest(state, run_dir)

    return state
