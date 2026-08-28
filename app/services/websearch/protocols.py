"""Protocol for the live web search used by the Retrieve stage."""

from __future__ import annotations

from typing import Protocol

from app.services.websearch.models import WebResult


class WebSearchService(Protocol):
    """Live internet search (search-then-inject).

    Implementations wrap a REST provider (Tavily / Serper / DuckDuckGo) and
    return bounded, text-only results ready for prompt injection. A provider
    error propagates (httpx.HTTPError etc.) — the caller (RetrieveStage)
    records it and fails open, so a broken search API never blocks a turn.
    """

    async def search(self, query: str, *, limit: int = 5) -> list[WebResult]: ...
