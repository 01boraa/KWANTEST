from __future__ import annotations

import requests

from .. import config
from ..state import DraftContent, ImageItem, PublishResult


def publish_to_wordpress(content: DraftContent, image_set: list[ImageItem]) -> PublishResult:
    if not (config.WORDPRESS_URL and config.WORDPRESS_USER and config.WORDPRESS_APP_PASSWORD):
        raise RuntimeError(
            "api_keys.txt에 WORDPRESS_URL / WORDPRESS_USER / WORDPRESS_APP_PASSWORD가 필요합니다."
        )

    media_id = None
    if image_set:
        with open(image_set[0].path, "rb") as f:
            media_resp = requests.post(
                f"{config.WORDPRESS_URL}/wp-json/wp/v2/media",
                auth=(config.WORDPRESS_USER, config.WORDPRESS_APP_PASSWORD),
                headers={"Content-Disposition": f'attachment; filename="{image_set[0].section_id}.png"'},
                files={"file": f},
                timeout=60,
            )
        media_resp.raise_for_status()
        media_id = media_resp.json()["id"]

    post_resp = requests.post(
        f"{config.WORDPRESS_URL}/wp-json/wp/v2/posts",
        auth=(config.WORDPRESS_USER, config.WORDPRESS_APP_PASSWORD),
        json={
            "title": content.title,
            "content": content.body_md,
            "excerpt": content.meta_description or "",
            "status": "draft",
            **({"featured_media": media_id} if media_id else {}),
        },
        timeout=60,
    )
    post_resp.raise_for_status()
    data = post_resp.json()
    return PublishResult(
        platform="wordpress",
        post_id=str(data["id"]),
        url=data.get("link"),
        status="draft_created",
    )


def publish_to_instagram(content: DraftContent, image_set: list[ImageItem]) -> PublishResult:
    # [PLACEHOLDER — 미구현]
    # Instagram Graph API는 로컬 파일이 아니라 "공개 URL"로 접근 가능한 이미지만
    # 캐러셀 업로드에 사용할 수 있습니다. 지금은 이미지를 로컬(claude/Auto/output/images)에만
    # 저장하므로, 실제 업로드를 쓰려면 먼저 이미지를 S3/Cloudinary 등에 올려 공개 URL을
    # 받아오는 단계를 추가로 구현해야 합니다.
    raise NotImplementedError(
        "인스타그램 업로드는 아직 구현되지 않았습니다. "
        "이미지를 공개 URL로 호스팅하는 단계(S3/Cloudinary 등)를 먼저 추가해주세요."
    )


def run(content: DraftContent, image_set: list[ImageItem], target_format: str) -> PublishResult:
    if target_format == "blog":
        return publish_to_wordpress(content, image_set)
    return publish_to_instagram(content, image_set)
