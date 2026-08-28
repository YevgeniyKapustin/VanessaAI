"""Serper.dev search client (Google results as JSON) — alternative provider.

Cheaper than Tavily and returns raw Google titles/links/snippets; the snippet
may occasionally contain HTML entities, which the compose prompt tolerates
(they are plain text to the model). API key goes in the ``X-API-KEY`` header.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config.settings import settings
from app.services.websearch.models import WebResult

logger = logging.getLogger(__name__)

_SERPER_ENDPOINT = "https://google.serper.dev/search"


class SerperSearch:
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
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def search(self, query: str, *, limit: int = 5) -> list[WebResult]:
        if not self._api_key:
            logger.warning("serper_search_no_api_key query=%r", query)
            return []
        response = await self._http.post(
            _SERPER_ENDPOINT,
            json={"q": query, "num": max(1, limit)},
            headers={"X-API-KEY": self._api_key},
        )
        response.raise_for_status()
        return _parse_results(response.json())

    @staticmethod
    def provider_name() -> str:
        return "serper"


def _parse_results(data: dict[str, Any]) -> list[WebResult]:
    results: list[WebResult] = []
    for item in data.get("organic") or []:
        url = str(item.get("link") or "").strip()
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if not url or not (title or snippet):
            continue
        results.append(WebResult(title=title, url=url, snippet=snippet))
    return results
