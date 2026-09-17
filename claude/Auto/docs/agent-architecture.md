# 콘텐츠 생성 멀티 에이전트 시스템 설계

블로그 글 + 인스타그램 카드뉴스를 자동으로 리서치 → 작성 → 검수 → 이미지 생성 →
검증 → 업로드까지 처리하는 8단계 에이전트 파이프라인 설계 문서.

- **오케스트레이션**: ~~LangGraph~~ → 순수 Python (`claude/Auto/src/pipeline.py`).
  맥북에서 프레임워크 의존성 없이 바로 돌릴 수 있도록, 상태(dict/Pydantic 모델)를
  직접 들고 다니며 재시도/분기를 명시적인 `while` 루프로 구현하는 방식으로 변경.
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

모든 단계는 하나의 공유 `PipelineState`를 읽고 갱신하며, 검수 단계(B/D/F/G)
뒤에는 항상 재시도/라우팅 로직(`_check_retry`, `fault` 기반 분기)이 붙는다.
실제 구현은 `pipeline.py`의 `run_pipeline()` 함수 하나에 명시적으로 풀어 썼다.

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

모든 산출물(설계 문서, 코드, 프롬프트)은 리포지토리 루트의 `claude/Auto/` 아래에
모아서 관리한다.

```
claude/Auto/
  docs/
    agent-architecture.md    # 본 문서
  src/
    state.py                # PipelineState, 각 리포트/아이템 TypedDict 정의
    graph/
      pipeline.py            # 8단계 오케스트레이션 (재시도/라우팅을 직접 구현한 순수 Python)
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
    prompts/
      collector.md              # A
      verifier.md                # B
      writer.md                   # C
      editor.md                    # D
      image_generator.md            # E
      alignment_validator.md         # F
      supervisor.md                   # G
      _shared/
        style_guide_block.md         # 여러 프롬프트가 공유하는 브랜드 톤/컬러 블록
```

## 6. 에이전트 지침(프롬프트) 설계 방식

그래프 구조·상태 스키마·재시도 로직은 결정론적인 "배관"이지만, 실제 산출물의
품질은 **판단을 내리는 에이전트(B/D/F/G)의 프롬프트가 얼마나 엄격하고 일관된
기준을 갖고 있는가**에 좌우된다. 기준이 느슨하면 문제 있는 콘텐츠가 그대로
통과하고(과소 반려), 기준이 애매하게 엄격하면 멀쩡한 콘텐츠도 재시도 한도만
소모하다 사람 검토로 넘어간다(과다 반려). 그래서 프롬프트는 코드와 분리된
버전 관리 대상으로 취급한다.

### 6.1 코드와 프롬프트 분리

- 프롬프트는 `claude/Auto/src/prompts/{agent_name}.md`로 별도 파일화하고, 에이전트 코드는
  이 파일을 로드해 변수만 채워 넣는다. 프롬프트 튜닝 시 Python 코드를 건드릴
  필요가 없게 하기 위함.
- `style_guide`(브랜드 톤/컬러/타깃 독자) 같이 여러 에이전트(C/E/F/G)가 공통으로
  참조하는 내용은 `_shared/` 블록으로 분리해 한 곳만 고치면 전체에 반영되게 한다.

### 6.2 모든 프롬프트가 따르는 공통 템플릿

```
# Role
(이 에이전트가 무엇인지, 파이프라인에서의 위치)

# Inputs
(어떤 상태 필드가 주입되는지 — 예: fact_sheet, draft, style_guide)

# Task
(수행할 작업을 단계별로 명시. "알아서 잘 써줘" 금지, 구체적 절차로 분해)

# Rubric / Checklist   ← judge 에이전트(B/D/F/G)에 특히 중요
(통과/반려를 가르는 기준을 체크리스트로 명문화. "좋은지 판단하라" 같은
 애매한 지시가 아니라 "다음 항목을 모두 확인하고 하나라도 위반하면 fail")

# Output Schema
(Pydantic 모델과 1:1 매핑되는 JSON 스키마. 반려 시 사유(reason)와
 다음 에이전트가 참고할 구체적 수정 지시(feedback)를 반드시 포함)

# Examples (few-shot)
(judge 에이전트는 pass 예시 1개 + fail 예시 1개를 넣어 판정 기준을 보정)

# Constraints
(하지 말아야 할 것: 예 — 확인 안 된 사실을 단정적으로 쓰지 말 것 등)
```

### 6.3 Judge 에이전트(B/D/F/G) 프롬프트 원칙

1. **판정 기준을 수치/체크리스트로 명문화**한다. 예: B는 "동일 주장을 뒷받침하는
   독립 출처가 2개 이상이면 confidence 상향, 1개면 유지, 0개면 rejected".
2. **이지선다(pass/fail)만 반환하지 않는다.** 반려 시 사유와, 반려받는 에이전트가
   그대로 사용할 수 있는 구체적 수정 지시를 같이 출력해야 재작업 루프가 의미 있다.
3. **few-shot pass/fail 예시로 기준을 보정(calibration)**한다. 특히 F(조합 검증)처럼
   "무엇을 fault로 볼지"가 모델마다 편차가 큰 판단은 예시 없이는 일관성이 떨어진다.
4. **배포 후 실제 통과율을 로깅**해 너무 관대하거나(문제 있는 콘텐츠가 자주 통과)
   너무 엄격한지(재시도만 반복) 확인하고 rubric을 조정한다.

### 6.4 예시 스켈레톤

**`prompts/verifier.md` (B — 자료검증)**
```
# Role
너는 수집된 자료의 사실관계를 검증하는 팩트체커다.

# Inputs
- raw_sources: [{url, title, snippet, raw_text, fetched_at}]
- topic: str

# Task
1. raw_sources에서 topic과 관련된 핵심 주장(claim)들을 추출한다.
2. 각 claim에 대해 독립적인 출처가 몇 개나 이를 뒷받침하는지 확인한다.
3. 아래 confidence 규칙에 따라 각 claim을 채점한다.

# Rubric
- 독립 출처 2개 이상 일치 + 최근 1년 이내 게시 → confidence = "high"
- 독립 출처 1개만 존재, 또는 출처가 오래됨(1년 초과) → confidence = "medium"
- 뒷받침 출처 없음, 또는 출처끼리 상충 → confidence = "low" (claim 폐기)
- claim의 60% 이상이 "low"면 verify_report.pass = false

# Output Schema (JSON)
{
  "claims": [{"claim": str, "sources": [url], "confidence": "high"|"medium"|"low"}],
  "rejected_sources": [{"url": str, "reason": str}],
  "pass": bool,
  "reason": str,           // pass=false일 때 왜 반려했는지
  "feedback_for_collector": str | null  // pass=false일 때 재수집 시 참고할 지시
}

# Constraints
- 출처에 없는 내용을 추론해서 claim으로 만들지 말 것.
```

**`prompts/supervisor.md` (G — 총괄 검수)**
```
# Role
너는 파이프라인의 최종 게이트키퍼다. 개별 단계는 각자의 기준으로 통과했지만,
전체적으로 봤을 때 놓친 문제가 없는지 메타 리뷰한다.

# Inputs
- reviewed_content, image_set, fact_sheet, review_report, alignment_report, style_guide

# Task
1. 아래 체크리스트를 모두 확인한다.
2. 하나라도 fail이면 어느 단계로 되돌려야 하는지(fault_stage)를 명시한다.

# Rubric (모두 충족해야 approved=true)
- [ ] 톤/문체가 style_guide와 일관되는가
- [ ] 법적/민감 이슈(과장 광고, 저작권, 개인정보)가 없는가
- [ ] fact_sheet 상 confidence="low"였던 내용이 본문에 단정적으로 남아있지 않은가
- [ ] 카드뉴스: 슬라이드 수와 이미지 수가 정확히 일치하는가 / 블로그: 대표 이미지 존재하는가
- [ ] 업로드 대상 플랫폼의 필수 필드(제목, alt text, 해시태그 등)가 모두 채워졌는가

# Output Schema (JSON)
{
  "approved": bool,
  "failed_checks": [str],
  "fault_stage": "writer"|"editor"|"image_generator"|"alignment_validator"|null,
  "notes": str
}
```

### 6.5 버전 관리 및 회귀 테스트

- 프롬프트 파일에 버전을 명시하고(`<!-- v1.2 -->` 등) 변경 이력을 남긴다.
- 각 judge 에이전트마다 "입력 → 기대 pass/fail" fixture 셋(예: 의도적으로 사실
  왜곡을 넣은 draft, 의도적으로 이미지-텍스트가 안 맞는 케이스)을 만들어 두고,
  프롬프트를 수정할 때마다 이 회귀 셋으로 판정이 여전히 맞는지 확인한다.

## 7. 다음 단계 (구현 시 고려사항)

- 포맷 분기(블로그 vs 카드뉴스)는 `target_format`을 각 에이전트 프롬프트/로직에서
  분기 처리하되, 상태 스키마와 그래프 구조는 공유하는 것을 권장 (완전히 다른
  파이프라인 두 개를 만들지 않기 위함).
- B/D/F/G의 각 리포트는 구조화된 출력(JSON/Pydantic 모델)으로 강제해야 라우팅
  로직이 문자열 파싱 없이 안정적으로 동작한다.
- 실제 구현 단계에서는 각 에이전트의 프롬프트, 사용할 LLM/이미지 모델, 재시도
  한도(`max_retries`) 등을 별도 설정 파일로 분리하는 것을 권장한다.
  → `claude/Auto/api_keys.txt`(모델/재시도 한도)로 구현됨.

## 8. 구현 현황 (리얼아카데미 대상)

- **대상**: 초등 교육 브랜드 "리얼아카데미"의 학부모 대상 콘텐츠
  (블로그 2500자 내외 + 이미지, 또는 인스타 카드뉴스 8장 + 이미지)
- **텍스트 LLM**: Anthropic Claude Sonnet 5 (`ANTHROPIC_API_KEY`)
- **이미지 생성**: OpenAI Image API (`OPENAI_API_KEY`, 모델 ID는 `api_keys.txt`에서 직접 지정)
- **자료수집**: DuckDuckGo 검색 (키 불필요, 기본 내장 — 필요 시 교체 가능)
- **업로드**: 블로그는 WordPress REST API로 구현(초안 상태로 생성), 인스타는
  이미지 공개 URL 호스팅이 선행되어야 해서 아직 미구현 (설계만 반영, 수동 업로드 전제)
- **구조적 검증**: 슬라이드 수(8장)·슬라이드 글자수·블로그 글자수(2500자 ±15%)처럼
  "셀 수 있는" 기준은 LLM 판단이 아니라 `src/validators.py`에서 코드로 결정론적으로
  검증한다. D(글검수)에서 LLM 판정과 이 구조 검증을 합쳐, 구조 기준을 하나라도
  어기면 LLM이 통과라고 해도 무조건 반려된다.
- **검증**: `tests/test_pipeline_mock.py`에서 LLM/이미지 API를 mock으로 대체해
  재시도 카운팅, `fault` 기반 반려 라우팅, 재시도 한도 초과 시 사람 검토 전환,
  구조적 검증 강제를 실제로 실행해 확인함 (2026-09-17 기준 전부 통과).

## 9. 사람 개입 체크포인트 (2곳)

완전 자동화는 리스크가 크다고 판단해, 파이프라인 안에 사람이 반드시 확인하고
`y`를 눌러야 다음 단계로 넘어가는 지점을 정확히 2곳 두었다 (`pipeline.py`의
`_human_checkpoint`). `interactive=False`로 실행하면 테스트용으로 건너뛸 수 있다.

1. **사실검증 확인** (B 통과 직후, C 글쓰기 시작 전)
   - 잘못된 사실 위에서 글/이미지가 만들어지면 이후 모든 단계(작성→검수→이미지
     →조합검증→총괄)가 그 위에서 헛돈다. 가장 이른 시점에 사람이 `fact_sheet`
     (검증된 주장과 출처)를 훑어보고 진행 여부를 결정한다.
   - `run_dir/fact_sheet.json`에 저장되어 터미널 요약 외에 상세 내용도 확인 가능.
2. **최종 발행 승인** (G 총괄 승인 직후, H 업로드 직전)
   - 개별 검수를 다 통과했더라도 업로드(공개) 전 마지막 안전장치. 블로그는
     WordPress에 초안으로만 올라가지만, 그래도 사람이 최종 확인 후 진행하도록 함.
   - `run_dir/preview.html`을 브라우저로 열어 글+이미지 조합을 실제로 보고 판단.

각 체크포인트에서 `n`을 입력하면 `HumanRejected` 예외로 파이프라인이 멈추고,
저장된 파일을 검토/수정한 뒤 다시 실행하면 된다.

## 10. 결과물(글+이미지) 저장 구조

클라우드 저장소 없이 **로컬 폴더 하나**에 실행마다 결과를 모아 저장한다
(`src/storage.py`). 이유: (1) 지금은 인스타 업로드가 수동이라 사람이 직접
파일을 찾아 올릴 수 있어야 하고, (2) 위 체크포인트 2곳에서 사람이 바로
확인할 수 있는 위치가 필요하며, (3) 별도 인프라(S3 등) 없이 맥북에서 바로
돌아가야 하기 때문.

```
claude/Auto/output/runs/{YYYYMMDD_HHMMSS}_{주제-슬러그}/
  fact_sheet.json        # 체크포인트 1용 — 검증된 주장/출처 전체
  article.md              # blog: 제목+본문+메타설명+해시태그
  slides.md                # card_news: 슬라이드별 텍스트
  images/                   # 생성된 이미지 원본 (slide-1.png ... 또는 cover.png)
  images_manifest.json       # 이미지별 prompt/alt_text 기록
  preview.html                 # 체크포인트 2용 — 글+이미지를 브라우저로 한 번에 확인
  manifest.json                 # 전체 PipelineState 스냅샷 (리포트 포함, 감사/디버그용)
```

`output/`는 git에 올리지 않는다(`.gitignore`). 인스타 카드뉴스를 수동 업로드할
때는 이 폴더의 `images/`에서 이미지를, `slides.md`에서 캡션 문구를 그대로
가져다 쓰면 된다. 나중에 인스타 자동 업로드를 붙일 경우, 이 로컬 이미지를
S3/Cloudinary 등에 올려 공개 URL을 얻는 단계만 추가하면 되도록 구조를
분리해뒀다 (`src/agents/publisher.py`의 `publish_to_instagram` 참고).
