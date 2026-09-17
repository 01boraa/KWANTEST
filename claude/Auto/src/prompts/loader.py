from __future__ import annotations

from pathlib import Path

from ..state import StyleGuide

PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def render_style_guide(style_guide: StyleGuide) -> str:
    template = (PROMPTS_DIR / "_shared" / "style_guide_block.md").read_text(encoding="utf-8")
    return template.format(
        tone=style_guide.tone,
        target_audience=style_guide.target_audience,
        brand_colors=", ".join(style_guide.brand_colors) or "지정 없음",
        max_slide_chars=style_guide.max_slide_chars,
        card_news_slide_count=style_guide.card_news_slide_count,
        blog_target_chars=style_guide.blog_target_chars,
    )
