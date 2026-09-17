from __future__ import annotations

from .state import DraftContent, StyleGuide

# 슬라이드 수/글자수처럼 "셀 수 있는" 기준은 LLM 판단에 맡기지 않고 코드로
# 결정론적으로(매번 같은 결과가 나오게) 검증한다. LLM 검수(editor.md)는 문법/톤/
# 사실관계처럼 판단이 필요한 부분만 담당한다.


def structural_issues(
    draft: DraftContent, style_guide: StyleGuide, target_format: str
) -> list[str]:
    issues: list[str] = []

    if target_format == "card_news":
        expected = style_guide.card_news_slide_count
        actual = len(draft.slides)
        if actual != expected:
            issues.append(
                f"[구조] 슬라이드가 {actual}장입니다. 정확히 {expected}장으로 맞춰야 합니다."
            )
        for s in draft.slides:
            if len(s.text) > style_guide.max_slide_chars:
                issues.append(
                    f"[구조] 슬라이드 {s.order}: 글자수 {len(s.text)}자가 "
                    f"최대 {style_guide.max_slide_chars}자를 초과합니다."
                )
            if not s.image_prompt:
                issues.append(f"[구조] 슬라이드 {s.order}: image_prompt가 비어 있습니다.")
    else:
        body = draft.body_md or ""
        char_count = len(body.replace(" ", "").replace("\n", ""))
        target = style_guide.blog_target_chars
        low, high = target * 0.85, target * 1.15
        if not (low <= char_count <= high):
            issues.append(
                f"[구조] 본문 글자수가 {char_count}자입니다. "
                f"목표 {target}자(±15%, {int(low)}~{int(high)}자) 범위를 벗어났습니다."
            )
        if not draft.meta_description:
            issues.append("[구조] meta_description이 비어 있습니다.")
        if not draft.hashtags:
            issues.append("[구조] hashtags가 비어 있습니다.")

    return issues
