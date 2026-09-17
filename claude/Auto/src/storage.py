from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from .state import DraftContent, ImageItem, PipelineState

# 실행 결과(글+이미지+리포트)는 output/runs/{시각}_{주제 슬러그}/ 폴더 하나에
# 전부 모아서 로컬에 저장한다. 클라우드 저장소 없이도 Finder에서 바로 열어보고,
# 사람 검토 체크포인트에서 preview.html로 빠르게 확인할 수 있게 하기 위함.


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^0-9A-Za-z가-힣]+", "-", text).strip("-")
    return slug[:max_len] or "untitled"


def make_run_dir(topic: str, base_dir: Path) -> Path:
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = base_dir / "runs" / f"{timestamp}_{slugify(topic)}"
    (run_dir / "images").mkdir(parents=True, exist_ok=True)
    return run_dir


def _save_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_fact_sheet(state: PipelineState, run_dir: Path) -> None:
    _save_json(state.fact_sheet.model_dump(mode="json"), run_dir / "fact_sheet.json")


def save_content(
    content: DraftContent,
    image_set: list[ImageItem],
    target_format: str,
    run_dir: Path,
) -> None:
    if target_format == "blog":
        text = (
            f"# {content.title}\n\n{content.body_md or ''}\n\n---\n"
            f"메타 설명: {content.meta_description}\n"
            f"해시태그: {' '.join(content.hashtags)}\n"
        )
        (run_dir / "article.md").write_text(text, encoding="utf-8")
    else:
        lines = [f"# {content.title}\n"]
        for s in sorted(content.slides, key=lambda s: s.order):
            lines.append(f"## 슬라이드 {s.order}\n{s.text}\n")
        lines.append(f"\n해시태그: {' '.join(content.hashtags)}\n")
        (run_dir / "slides.md").write_text("\n".join(lines), encoding="utf-8")

    _save_json(
        {"title": content.title, "images": [i.model_dump(mode="json") for i in image_set]},
        run_dir / "images_manifest.json",
    )


def save_preview_html(
    content: DraftContent,
    image_set: list[ImageItem],
    target_format: str,
    run_dir: Path,
) -> Path:
    images_by_section = {i.section_id: i for i in image_set}
    blocks: list[str] = []

    if target_format == "card_news":
        for s in sorted(content.slides, key=lambda s: s.order):
            img = images_by_section.get(f"slide-{s.order}")
            img_tag = (
                f'<img src="images/{Path(img.path).name}" style="max-width:360px;display:block;">'
                if img
                else "<em>(이미지 없음)</em>"
            )
            blocks.append(
                f'<div style="margin-bottom:28px;">'
                f"<h3>슬라이드 {s.order}</h3>{img_tag}"
                f"<p>{s.text}</p></div>"
            )
    else:
        img = images_by_section.get("cover")
        img_tag = (
            f'<img src="images/{Path(img.path).name}" style="max-width:480px;display:block;">'
            if img
            else "<em>(이미지 없음)</em>"
        )
        body_html = (content.body_md or "").replace("\n", "<br>")
        blocks.append(f"<h1>{content.title}</h1>{img_tag}<div>{body_html}</div>")

    html = (
        '<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
        f"<title>{content.title} - 미리보기</title></head>"
        '<body style="font-family: sans-serif; max-width: 720px; margin: 40px auto;">'
        f"{''.join(blocks)}</body></html>"
    )

    out_path = run_dir / "preview.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


def save_manifest(state: PipelineState, run_dir: Path) -> None:
    _save_json(state.model_dump(mode="json"), run_dir / "manifest.json")
