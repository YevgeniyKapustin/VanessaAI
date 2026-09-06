"""Factory that instantiates the configured web-search provider."""

from __future__ import annotations

import logging

from vanessa.config.settings import settings
from vanessa.infrastructure.mcp.client import FailOpenMcpClient, StreamableHttpMcpClient
from vanessa.infrastructure.mcp.websearch import McpWebSearch
from vanessa.infrastructure.websearch.duckduckgo import DuckDuckGoSearch
from vanessa.infrastructure.websearch.protocols import WebSearchService
from vanessa.infrastructure.websearch.serper import SerperSearch
from vanessa.infrastructure.websearch.tavily import TavilySearch

logger = logging.getLogger(__name__)


def _mcp_web_search() -> McpWebSearch | None:
    mcp_url = settings.mcp_websearch_url.strip()
    if not mcp_url:
        return None
    client = FailOpenMcpClient(
        StreamableHttpMcpClient(
            mcp_url,
            timeout=settings.mcp_timeout_seconds,
        ),
        fail_open=settings.mcp_fail_open,
        fallback="[]",
    )
    logger.info("web_search_transport=mcp url=%s", mcp_url)
    return McpWebSearch(client, max_results=settings.web_search_max_results)


def _provider_search(provider: str) -> WebSearchService:
    if provider == "serper":
        return SerperSearch()
    if provider == "duckduckgo":
        return DuckDuckGoSearch()
    if provider != "tavily":
        logger.warning(
            "web_search_unknown_provider provider=%r, falling back to tavily",
            provider,
        )
    return TavilySearch()


def _local_web_search() -> WebSearchService | None:
    if not settings.web_search_enabled:
        return None
    return _provider_search(settings.web_search_provider.strip().lower())


def create_web_search(*, allow_mcp: bool = True) -> WebSearchService | None:
    """Instantiate the configured search provider, or None when disabled.

    When ``MCP_WEBSEARCH_URL`` is set, the search is delegated to the
    mcp-websearch server (fail-open via the circuit breaker); otherwise the
    in-process provider is used. Returns None when search is fully disabled so
    a deployment without a search API behaves exactly as before.

    MCP servers must call with ``allow_mcp=False`` so they never recurse into
    themselves via the shared ConfigMap URL.
    """
    if allow_mcp:
        mcp_search = _mcp_web_search()
        if mcp_search is not None:
            return mcp_search
    return _local_web_search()
