from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class SourceItem(BaseModel):
    url: str
    title: str
    snippet: str
    raw_text: str
    fetched_at: str


class Claim(BaseModel):
    claim: str
    sources: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]


class RejectedSource(BaseModel):
    url: str
    reason: str


class FactSheet(BaseModel):
    claims: list[Claim] = Field(default_factory=list)
    rejected_sources: list[RejectedSource] = Field(default_factory=list)


class VerifyReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pass_: bool = Field(alias="pass")
    reason: str
    feedback_for_collector: Optional[str] = None


class Slide(BaseModel):
    order: int
    text: str
    image_prompt: str


class DraftContent(BaseModel):
    title: str
    body_md: Optional[str] = None
    slides: list[Slide] = Field(default_factory=list)
    meta_description: Optional[str] = None
    hashtags: list[str] = Field(default_factory=list)


class ReviewReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pass_: bool = Field(alias="pass")
    issues: list[str] = Field(default_factory=list)


class ImageItem(BaseModel):
    section_id: str
    path: str
    prompt: str
    alt_text: str


class AlignmentReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pass_: bool = Field(alias="pass")
    mismatches: list[str] = Field(default_factory=list)
    fault: Optional[Literal["text", "image"]] = None


class FinalApproval(BaseModel):
    approved: bool
    failed_checks: list[str] = Field(default_factory=list)
    fault_stage: Optional[
        Literal["writer", "editor", "image_generator", "alignment_validator"]
    ] = None
    notes: str = ""


class PublishResult(BaseModel):
    platform: str
    post_id: Optional[str] = None
    url: Optional[str] = None
    status: str


class StyleGuide(BaseModel):
    tone: str = "친근하고 신뢰감 있는 정보 전달형 (과장 광고성 문구 지양)"
    target_audience: str = "초등학생 자녀를 둔 학부모"
    brand_colors: list[str] = Field(default_factory=list)
    max_slide_chars: int = 60
    card_news_slide_count: int = 8
    blog_target_chars: int = 2500


class PipelineState(BaseModel):
    topic: str
    target_format: Literal["blog", "card_news"]
    style_guide: StyleGuide

    raw_sources: list[SourceItem] = Field(default_factory=list)
    fact_sheet: Optional[FactSheet] = None
    verify_report: Optional[VerifyReport] = None

    draft: Optional[DraftContent] = None

    review_report: Optional[ReviewReport] = None
    reviewed_content: Optional[DraftContent] = None

    image_set: list[ImageItem] = Field(default_factory=list)

    alignment_report: Optional[AlignmentReport] = None

    final_approval: Optional[FinalApproval] = None

    publish_result: Optional[PublishResult] = None

    retry_counts: dict[str, int] = Field(default_factory=dict)
    max_retries: int = 2
    human_review_needed: bool = False
    human_review_reason: str = ""
