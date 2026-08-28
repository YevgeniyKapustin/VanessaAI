"""DuckDuckGo search client — free but unofficial / best-effort.

Hits the public HTML endpoint (no API key). DuckDuckGo has no official search
API for this use case and may rate-limit or block datacenter IPs, so this
provider is strictly best-effort: any HTTP or parsing trouble returns an empty
list and the caller fails open. Prefer Tavily (default) or Serper for
production.
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any

import httpx

from app.config.settings import settings
from app.services.websearch.models import WebResult

logger = logging.getLogger(__name__)

_DDG_ENDPOINT = "https://html.duckduckgo.com/html/"

# One <a rel="nofollow" class="result__a" href="...">title</a> per result,
# followed (in the same <div class="result">) by the snippet paragraph.
_RESULT_LINK_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_SNIPPET_RE = re.compile(
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


class DuckDuckGoSearch:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
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
        try:
            response = await self._http.post(
                _DDG_ENDPOINT,
                data={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (compatible; VanessaAI/1.0)"},
            )
            response.raise_for_status()
            return _parse_results(response.text, limit=limit)
        except (httpx.HTTPError, ValueError) as exc:
            # Best-effort provider: never let DDG flakiness surface upstream.
            logger.warning("duckduckgo_search_failed query=%r error=%s", query, exc)
            return []

    @staticmethod
    def provider_name() -> str:
        return "duckduckgo"


def _clean(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _parse_results(page: str, *, limit: int) -> list[WebResult]:
    links = _RESULT_LINK_RE.findall(page)
    snippets = [m for m in _SNIPPET_RE.findall(page)]
    results: list[WebResult] = []
    for index, (href, title_html) in enumerate(links[:limit]):
        url = html.unescape(href)
        title = _clean(title_html)
        if not url or not title:
            continue
        snippet = _clean(snippets[index]) if index < len(snippets) else ""
        results.append(WebResult(title=title, url=url, snippet=snippet))
    return results
