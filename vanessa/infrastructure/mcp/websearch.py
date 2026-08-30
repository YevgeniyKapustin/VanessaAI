"""WebSearchService adapter backed by the mcp-websearch server.

Keeps the agent core's Retrieve stage untouched: the adapter implements the
same ``WebSearchService.search()`` protocol, so swapping the in-process
provider for the MCP server is a config-only change.
"""

from __future__ import annotations

import json
import logging

from vanessa.core.messages import WebResult
from vanessa.infrastructure.mcp.protocols import McpClientProtocol

logger = logging.getLogger(__name__)


class McpWebSearch:
    def __init__(self, client: McpClientProtocol, *, max_results: int = 5) -> None:
        self._client = client
        self._max_results = max_results

    async def search(self, query: str, *, limit: int = 5) -> list[WebResult]:
        raw = await self._client.call_tool(
            "web_search",
            {"query": query, "limit": max(1, min(limit, self._max_results))},
        )
        return _parse_results(raw)


def _parse_results(raw: str) -> list[WebResult]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        logger.warning("mcp_web_search_unparseable raw=%r", raw[:200])
        return []
    if not isinstance(data, list):
        return []
    results: list[WebResult] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        results.append(
            WebResult(
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                snippet=str(item.get("snippet", "")),
                published_date=item.get("published_date"),
            )
        )
    return results
