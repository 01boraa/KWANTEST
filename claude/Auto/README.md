# claude/Auto — 리얼아카데미 콘텐츠 자동 생성 파이프라인

초등 교육 브랜드 "리얼아카데미"의 학부모 대상 콘텐츠(블로그 2500자 내외 + 이미지,
또는 인스타 카드뉴스 8장 + 이미지)를 자동으로 리서치→작성→검수→이미지 생성→
검증→업로드까지 처리하는 순수 Python 파이프라인입니다. (LangGraph 미사용,
직접 작성한 재시도/라우팅 루프)

설계 배경은 `docs/agent-architecture.md` 참고.

## ⚠️ 지금 상태: 스켈레톤

각 에이전트의 프롬프트(`src/prompts/*.md`)는 실제 편집 기준이 아니라 **초안
(placeholder)**입니다. 파일 상단에 `[PLACEHOLDER — 검토 필요]` 주석이 있는
곳은 반드시 검토 후 사용하세요. 코드는 건드리지 않고 이 `.md` 파일만 고치면
됩니다.

## 맥북에서 실행하기

```bash
cd claude/Auto

# 1) 가상환경 (최초 1회)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2) API 키 설정 (최초 1회)
cp api_keys.example.txt api_keys.txt
# api_keys.txt를 아무 텍스트 편집기로 열어서 값 채워넣기

# 3) 실행
python main.py "초등 저학년 문해력 향상 방법" --format blog
python main.py "초등 저학년 문해력 향상 방법" --format card_news
```

## 사용하는 API

- **텍스트(글쓰기/검수/총괄)**: Anthropic Claude API (`ANTHROPIC_API_KEY`, 기본 모델 `claude-sonnet-5`)
- **이미지 생성**: OpenAI Image API (`OPENAI_API_KEY`, 모델명은 `api_keys.txt`의
  `OPENAI_IMAGE_MODEL`에서 직접 지정 — 정확한 모델 ID는 OpenAI 문서에서 확인)
- **자료수집(웹 검색)**: DuckDuckGo (API 키 불필요, 기본 내장). 검색 품질이
  부족하면 `src/agents/collector.py`를 다른 검색 API로 교체하세요.

## 알려진 제약 / 다음에 해야 할 일

- **인스타그램 업로드(H, card_news)는 미구현**입니다. Instagram Graph API는
  이미지가 공개 URL로 호스팅되어 있어야 하는데, 지금은 이미지를 로컬
  (`output/images/`)에만 저장합니다. S3/Cloudinary 등에 업로드해 공개 URL을
  받아오는 단계를 `src/agents/publisher.py`에 추가해야 실제 업로드가 됩니다.
- **블로그 업로드(H)는 WordPress REST API 기준으로 구현**되어 있습니다
  (`WORDPRESS_URL/wp-json/wp/v2/posts`, 애플리케이션 비밀번호 인증). 초안
  상태(`status: draft`)로 올라가며, 검토 후 직접 발행하도록 되어 있습니다.
  다른 블로그 플랫폼을 쓰신다면 이 파일을 교체하세요.
- 프롬프트 파일들의 판정 기준(과장 광고 문구 목록, 슬라이드 구성 방식 등)을
  실제 운영 기준에 맞게 다듬어야 합니다.

## 디렉토리 구조

```
claude/Auto/
  README.md
  requirements.txt
  api_keys.example.txt   # 템플릿 (git 포함)
  api_keys.txt            # 실제 키 (git 제외, 직접 생성)
  main.py                  # 실행 진입점
  docs/
    agent-architecture.md   # 설계 문서
  src/
    config.py                # api_keys.txt 로드
    state.py                   # PipelineState 등 Pydantic 모델
    llm_client.py                # Anthropic 호출 래퍼
    image_client.py                # OpenAI 이미지 호출 래퍼
    pipeline.py                      # 8단계 오케스트레이션 (재시도/라우팅)
    agents/                           # A~H 각 에이전트
    prompts/                          # 에이전트별 지침(.md), 여기만 수정하면 됨
  output/                 # 실행 결과물 (이미지 등, git 제외)
```
