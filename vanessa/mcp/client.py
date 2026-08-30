"""MCP client (Streamable HTTP) with fail-open + circuit breaker.

The agent core never imports MCP server code: it calls tools over the wire.
``StreamableHttpMcpClient`` opens a stateless session per call;
``FailOpenMcpClient`` adds a circuit breaker and, by default, degrades instead
of raising so a dead MCP server can never block a turn.
"""

from __future__ import annotations

import asyncio
import logging

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent

from vanessa.mcp.circuit_breaker import CircuitBreaker
from vanessa.mcp.protocols import McpClientProtocol

logger = logging.getLogger(__name__)


class StreamableHttpMcpClient:
    """Stateless MCP client over the Streamable HTTP transport."""

    def __init__(self, url: str, *, timeout: float = 10.0) -> None:
        self._url = url
        self._timeout = timeout

    async def call_tool(self, name: str, arguments: dict) -> str:
        async def _call() -> str:
            async with streamable_http_client(self._url) as (
                read,
                write,
                _get_session_id,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
                    return _text_from_result(result)

        return await asyncio.wait_for(_call(), timeout=self._timeout)


class FailOpenMcpClient:
    """Wraps a client with a circuit breaker + optional fail-open fallback."""

    def __init__(
        self,
        client: McpClientProtocol,
        *,
        breaker: CircuitBreaker | None = None,
        fail_open: bool = True,
        fallback: str = "[]",
    ) -> None:
        self._client = client
        self._breaker = breaker or CircuitBreaker()
        self._fail_open = fail_open
        self._fallback = fallback

    async def call_tool(self, name: str, arguments: dict) -> str:
        if not self._breaker.allow_request():
            logger.warning("mcp_circuit_open tool=%s", name)
            return self._fallback
        try:
            result = await self._client.call_tool(name, arguments)
        except Exception as exc:  # noqa: BLE001 - any transport/tool error
            self._breaker.record_failure()
            logger.warning("mcp_call_failed tool=%s error=%s", name, exc)
            if not self._fail_open:
                raise
            return self._fallback
        self._breaker.record_success()
        return result


def _text_from_result(result: CallToolResult) -> str:
    parts: list[str] = []
    for item in result.content or []:
        if isinstance(item, TextContent):
            parts.append(item.text)
        elif hasattr(item, "text"):
            parts.append(str(item.text))
    return "\n".join(parts)
