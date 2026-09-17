# 콘텐츠 생성 멀티 에이전트 시스템 설계

블로그 글 + 인스타그램 카드뉴스를 자동으로 리서치 → 작성 → 검수 → 이미지 생성 →
검증 → 업로드까지 처리하는 8단계 에이전트 파이프라인 설계 문서.

- **오케스트레이션**: LangGraph (StateGraph 기반, 조건부 엣지로 재시도/분기 처리)
- **산출물 형식**: 블로그 포스트(마크다운), 인스타 카드뉴스(슬라이드 세트)
- **핵심 설계 원칙**: 각 검수 단계는 반드시 "통과/반려 + 사유"를 반환하고,
  반려 시 원인이 된 단계로 되돌아간다 (무한루프 방지를 위한 재시도 카운터 필수).

## 1. 전체 파이프라인 개요

```
        ┌─────────────────────────────┐
        │                              │
        ▼                              │ (신뢰도 부족 → 재수집)
  A.자료수집 ──▶ B.자료검증 ──┐         │
                              │ pass   │
                              ▼        │
                         C.글쓰기 ◀────┘
                              │
                              ▼
                         D.글 검수 ──┐
                              │pass  │ fail → C로 반려(수정 지시 포함)
                              ▼      │
                         E.이미지 생성 ◀┘
                              │
                              ▼
                    F.글+이미지 조합 검증 ──┐
                              │ pass         │ fail → 원인에 따라
                              ▼              │   - 이미지 문제 → E
                         G.총괄 검수         │   - 텍스트 문제 → C
                              │ pass         ◀┘
                              ▼
                         H.업로드
                              │
                        (실패 → 재시도 N회 → 사람에게 알림)
```

LangGraph 관점에서는 모든 노드가 하나의 공유 `PipelineState`를 읽고 갱신하며,
검수 노드(B/D/F/G) 뒤에는 항상 조건부 엣지(`should_retry`, `route_failure`)가 붙는다.

## 2. 공유 상태 스키마 (`PipelineState`)

```python
class PipelineState(TypedDict):
    # 입력
    topic: str
    target_format: Literal["blog", "card_news"]
    style_guide: dict  # 톤, 타깃 독자, 브랜드 컬러/폰트, 글자수 제약 등

    # A→B
    raw_sources: list[SourceItem]        # {url, title, snippet, raw_text, fetched_at}

    # B→C
    fact_sheet: FactSheet                # {claims: [{claim, sources, confidence}], rejected_sources}
    verify_report: VerifyReport          # {pass: bool, reason: str}

    # C→D
    draft: DraftContent                  # {title, body_md | slides[], meta_description, hashtags}

    # D→E
    review_report: ReviewReport          # {pass: bool, issues: list[str]}
    reviewed_content: DraftContent

    # E→F
    image_set: list[ImageItem]           # {section_id, path/url, prompt, alt_text}

    # F→G
    alignment_report: AlignmentReport    # {pass: bool, mismatches: list[str], fault: "text"|"image"|None}

    # G→H
    final_approval: FinalApproval        # {approved: bool, notes: str}

    # H
    publish_result: PublishResult        # {platform, post_id, url, status}

    # 제어용
    retry_counts: dict[str, int]         # {"collect": 0, "write": 0, "image": 0, ...}
    max_retries: int                     # 기본 2~3
    human_review_needed: bool
```

## 3. 에이전트별 상세 설계

### A. 자료수집 에이전트 (Collector)
- **입력**: `topic`, (선택) 소스 화이트리스트/블랙리스트
- **도구**: 웹 검색 API, 뉴스/RSS API, 필요 시 특정 도메인 크롤러
- **출력**: `raw_sources`
- **재시도 트리거**: B에서 반려되면 검색 쿼리를 변형해 재수집 (`retry_counts["collect"]`)

### B. 자료검증/검수 에이전트 (Fact Verifier)
- **입력**: `raw_sources`
- **역할**:
  - 출처 신뢰도 평가 (도메인 권위, 게시일 최신성)
  - 동일 주장에 대한 다중 소스 교차 검증 → `confidence` 산출
  - 중복/스팸/광고성 소스 제거
- **출력**: `fact_sheet`, `verify_report`
- **게이트**: 평균 confidence < 임계값이면 `pass=False` → A로 반려

### C. 글쓰는 에이전트 (Writer)
- **입력**: `fact_sheet`, `style_guide`, `target_format`
- **역할**: 포맷에 맞춰 작성
  - 블로그: 제목, 본문(마크다운), 메타 설명, SEO 키워드
  - 카드뉴스: 슬라이드별 짧은 카피(장당 글자수 제한), 커버/CTA 슬라이드 포함
- **출력**: `draft`
- **반려 시 입력**: D 또는 F에서 넘어온 구체적 수정 지시(issues)를 프롬프트에 포함

### D. 글을 검수하는 에이전트 (Content Editor)
- **입력**: `draft`, `fact_sheet`(사실관계 재대조용)
- **역할**:
  - 문법/가독성/톤 일관성
  - `fact_sheet`와 대조해 사실 왜곡·과장 여부 확인
  - 표절/저작권 리스크, 포맷별 제약(카드뉴스 글자수, 블로그 SEO 체크리스트)
- **출력**: `review_report`, `reviewed_content`
- **게이트**: fail → C로 반려 (issues 목록 전달)

### E. 이미지를 생성하는 에이전트 (Image Generator)
- **입력**: `reviewed_content`, `style_guide`(브랜드 컬러/톤/폰트)
- **역할**:
  - 섹션/슬라이드별 이미지 프롬프트 설계
  - 이미지 생성 API 호출 (카드뉴스는 슬라이드 수만큼, 블로그는 대표+본문 삽입 이미지)
  - alt text 생성(접근성)
- **출력**: `image_set`

### F. 글+이미지 조합 검증 에이전트 (Alignment Validator)
- **입력**: `reviewed_content`, `image_set`
- **역할**:
  - 비전 모델로 이미지 설명을 생성해 본문/슬라이드 텍스트와 의미 일치도 확인
  - 카드뉴스 레이아웃 상 텍스트 오버플로우/가독성 체크
  - 브랜드 가이드(컬러/폰트) 준수 확인
- **출력**: `alignment_report` (`fault` 필드로 원인이 텍스트인지 이미지인지 표시)
- **게이트**:
  - `fault == "image"` → E로 반려 (이미지만 재생성)
  - `fault == "text"` → C로 반려 (이미지와 안 맞는 문구만 수정)

### G. 총괄 에이전트 (Supervisor / Final QA)
- **입력**: 지금까지의 모든 산출물과 리포트(`fact_sheet`, `review_report`, `alignment_report` 등)
- **역할**: LLM-as-judge 방식의 메타 리뷰
  - 개별 단계는 통과했지만 전체적으로 놓친 것 확인 (톤 일관성, 민감/법적 이슈, 최종 사실 재확인)
  - 업로드 포맷 최종 유효성 검증 (필드 누락, 이미지-슬라이드 개수 일치 등)
- **출력**: `final_approval`
- **게이트**: 미승인 시 사유에 따라 관련 단계로 반려, 또는 `human_review_needed=True`로 전환

### H. 업로드 에이전트 (Publisher)
- **입력**: `final_approval.approved == True`인 콘텐츠+이미지
- **역할**: 타깃 플랫폼 API 호출
  - 블로그: WordPress REST API / Ghost API 등
  - 인스타: Instagram Graph API (카드뉴스 캐러셀 업로드)
  - 예약 발행 여부 선택
- **출력**: `publish_result`
- **실패 처리**: 지수 백오프 재시도 → 그래도 실패 시 사람에게 알림(Slack/이메일) 후 종료

## 4. 재시도/무한루프 방지 전략

- 모든 반려 엣지는 `retry_counts[stage] += 1` 후 `max_retries` 초과 여부를 확인한다.
- 초과 시 자동 반려 대신 `human_review_needed=True`로 전환하고 파이프라인을 일시정지,
  사람이 직접 검토 후 재개(`resume`)하도록 한다.
- F(조합 검증)의 `fault` 판정처럼, "누구에게 반려할지"를 명확히 하는 필드를 리포트에
  반드시 포함시켜 라우팅 로직이 단순한 `if pass: next else: retry`에 머물지 않게 한다.

## 5. 제안 디렉토리 구조

```
src/
  state.py                # PipelineState, 각 리포트/아이템 TypedDict 정의
  graph/
    pipeline.py            # LangGraph StateGraph 정의, 조건부 엣지 라우팅 함수
  agents/
    collector.py            # A
    verifier.py              # B
    writer.py                 # C
    editor.py                  # D
    image_generator.py          # E
    alignment_validator.py       # F
    supervisor.py                 # G
    publisher.py                   # H
  tools/
    search_api.py            # A가 사용
    image_api.py              # E가 사용
    wordpress_client.py        # H가 사용 (블로그)
    instagram_client.py        # H가 사용 (카드뉴스)
docs/
  agent-architecture.md    # 본 문서
```

## 6. 다음 단계 (구현 시 고려사항)

- 포맷 분기(블로그 vs 카드뉴스)는 `target_format`을 각 에이전트 프롬프트/로직에서
  분기 처리하되, 상태 스키마와 그래프 구조는 공유하는 것을 권장 (완전히 다른
  파이프라인 두 개를 만들지 않기 위함).
- B/D/F/G의 각 리포트는 구조화된 출력(JSON/Pydantic 모델)으로 강제해야 라우팅
  로직이 문자열 파싱 없이 안정적으로 동작한다.
- 실제 구현 단계에서는 각 에이전트의 프롬프트, 사용할 LLM/이미지 모델, 재시도
  한도(`max_retries`) 등을 별도 설정 파일(`config.yaml`)로 분리하는 것을 권장한다.
