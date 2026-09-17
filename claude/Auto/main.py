from __future__ import annotations

import argparse

from src.pipeline import HumanRejected, HumanReviewNeeded, run_pipeline
from src.state import StyleGuide


def main() -> None:
    parser = argparse.ArgumentParser(
        description="리얼아카데미 초등 교육 콘텐츠 자동 생성 파이프라인 (블로그/카드뉴스)"
    )
    parser.add_argument("topic", help="콘텐츠 주제 (예: '초등 저학년 문해력 향상 방법')")
    parser.add_argument("--format", choices=["blog", "card_news"], default="blog")
    parser.add_argument("--tone", default=None, help="지정하지 않으면 StyleGuide 기본값 사용")
    parser.add_argument("--audience", default=None, help="지정하지 않으면 '초등학생 자녀를 둔 학부모'")
    parser.add_argument("--max-retries", type=int, default=2)
    args = parser.parse_args()

    style_guide = StyleGuide()
    if args.tone:
        style_guide.tone = args.tone
    if args.audience:
        style_guide.target_audience = args.audience

    try:
        state = run_pipeline(
            topic=args.topic,
            target_format=args.format,
            style_guide=style_guide,
            max_retries=args.max_retries,
        )
    except HumanReviewNeeded as e:
        print(f"\n[중단] '{e.stage}' 단계에서 사람 검토가 필요합니다: {e}")
        return
    except HumanRejected as e:
        print(f"\n[중단] '{e.stage}' 체크포인트에서 진행을 승인하지 않았습니다.")
        return

    print("\n=== 완료 ===")
    print(f"제목: {state.reviewed_content.title}")
    print(f"이미지 {len(state.image_set)}개 생성됨")
    print(f"업로드 결과: {state.publish_result}")


if __name__ == "__main__":
    main()
