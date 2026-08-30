"""Tavily AI search client (httpx, no SDK) — the default web-search provider.

Tavily is built for LLM retrieval: POST /search returns clean text snippets
(``content``), titles, urls and an optional ``published_date`` — ready for
prompt injection without any HTML stripping.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from vanessa.config.settings import settings
from vanessa.infrastructure.websearch.models import WebResult

logger = logging.getLogger(__name__)

_TAVILY_ENDPOINT = "https://api.tavily.com/search"


class TavilySearch:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.web_search_api_key
        self._client = client
        self._timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.web_search_timeout_seconds
        )

    @property
    def _http(self) -> httpx.AsyncClient:
        # One long-lived client per service instance (reused across turns);
        # tests inject their own mock client.
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def search(self, query: str, *, limit: int = 5) -> list[WebResult]:
        if not self._api_key:
            logger.warning("tavily_search_no_api_key query=%r", query)
            return []
        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max(1, limit),
            # Basic depth: 5 fast snippets, enough for a chat answer without
            # the (slower, costlier) full-page content extraction.
            "search_depth": "basic",
            "include_answer": False,
        }
        response = await self._http.post(_TAVILY_ENDPOINT, json=payload)
        response.raise_for_status()
        return _parse_results(response.json())

    @staticmethod
    def provider_name() -> str:
        return "tavily"


def _parse_results(data: dict[str, Any]) -> list[WebResult]:
    results: list[WebResult] = []
    for item in data.get("results") or []:
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or "").strip()
        if not url or not (title or content):
            continue
        results.append(
            WebResult(
                title=title,
                url=url,
                snippet=content,
                published_date=(
                    str(item.get("published_date") or "").strip() or None
                ),
            )
        )
    return results
