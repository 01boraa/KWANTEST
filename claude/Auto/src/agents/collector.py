from __future__ import annotations

import datetime as dt

from duckduckgo_search import DDGS

from ..state import SourceItem

# [PLACEHOLDER — 검토 필요]
# DuckDuckGo 검색은 API 키가 필요 없어 바로 동작하는 기본값으로 넣었습니다.
# 검색 품질이 부족하면 Tavily, SerpAPI, Google Custom Search 등 유료 API로 교체하세요.


def search_web(query: str, max_results: int = 8) -> list[SourceItem]:
    sources: list[SourceItem] = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            sources.append(
                SourceItem(
                    url=r.get("href", ""),
                    title=r.get("title", ""),
                    snippet=r.get("body", ""),
                    raw_text=r.get("body", ""),
                    fetched_at=dt.datetime.utcnow().isoformat(),
                )
            )
    return sources


def run(topic: str, feedback: str | None = None, max_results: int = 8) -> list[SourceItem]:
    query = topic if not feedback else f"{topic} {feedback}"
    return search_web(query, max_results=max_results)
