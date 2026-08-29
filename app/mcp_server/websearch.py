"""MCP server: live web search (wraps the configured search provider).

Exposes one ``web_search`` tool that returns text-only results as JSON, ready
for prompt injection — the same contract the in-process Retrieve stage uses.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict

from mcp.server.fastmcp import FastMCP

from app.services.websearch.factory import create_web_search
from app.services.websearch.protocols import WebSearchService

logger = logging.getLogger(__name__)


def build_server(provider: WebSearchService | None = None) -> FastMCP:
    """Build the websearch MCP server (provider injectable for tests)."""
    search = provider if provider is not None else create_web_search()
    server = FastMCP(
        name="vanessa-websearch",
        instructions="Live web search for the Vanessa agent. Returns JSON "
        "results [{title,url,snippet,published_date}].",
    )

    @server.tool(
        name="web_search",
        description=(
            "Search the live web and return text-only results as a JSON array "
            "of {title, url, snippet, published_date}."
        ),
    )
    async def web_search(query: str, limit: int = 5) -> str:
        if search is None:
            return "[]"
        results = await search.search(query, limit=max(1, min(limit, 10)))
        return json.dumps(
            [asdict(result) for result in results],
            ensure_ascii=False,
        )

    return server
