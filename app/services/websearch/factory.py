"""Factory that instantiates the configured web-search provider."""

from __future__ import annotations

import logging

from app.config.settings import settings
from app.services.websearch.duckduckgo import DuckDuckGoSearch
from app.services.websearch.protocols import WebSearchService
from app.services.websearch.serper import SerperSearch
from app.services.websearch.tavily import TavilySearch

logger = logging.getLogger(__name__)


def create_web_search() -> WebSearchService | None:
    """Instantiate the configured search provider, or None when disabled.

    When ``MCP_WEBSEARCH_URL`` is set, the search is delegated to the
    mcp-websearch server (fail-open via the circuit breaker); otherwise the
    in-process provider is used. Returns None when search is fully disabled so
    a deployment without a search API behaves exactly as before.
    """
    mcp_url = settings.mcp_websearch_url.strip()
    if mcp_url:
        from app.mcp.client import FailOpenMcpClient, StreamableHttpMcpClient
        from app.mcp.websearch import McpWebSearch

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
