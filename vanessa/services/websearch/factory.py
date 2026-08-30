"""Factory that instantiates the configured web-search provider."""

from __future__ import annotations

import logging

from vanessa.config.settings import settings
from vanessa.services.websearch.duckduckgo import DuckDuckGoSearch
from vanessa.services.websearch.protocols import WebSearchService
from vanessa.services.websearch.serper import SerperSearch
from vanessa.services.websearch.tavily import TavilySearch

logger = logging.getLogger(__name__)


def create_web_search(*, allow_mcp: bool = True) -> WebSearchService | None:
    """Instantiate the configured search provider, or None when disabled.

    When ``MCP_WEBSEARCH_URL`` is set, the search is delegated to the
    mcp-websearch server (fail-open via the circuit breaker); otherwise the
    in-process provider is used. Returns None when search is fully disabled so
    a deployment without a search API behaves exactly as before.

    MCP servers must call with ``allow_mcp=False`` so they never recurse into
    themselves via the shared ConfigMap URL.
    """
    mcp_url = settings.mcp_websearch_url.strip()
    if allow_mcp and mcp_url:
        from vanessa.mcp.client import FailOpenMcpClient, StreamableHttpMcpClient
        from vanessa.mcp.websearch import McpWebSearch

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

    if not settings.web_search_enabled:
        return None
    provider = settings.web_search_provider.strip().lower()
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
