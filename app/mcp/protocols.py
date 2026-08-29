"""Agent-core MCP client protocol."""

from __future__ import annotations

from typing import Protocol


class McpClientProtocol(Protocol):
    """A client that can invoke a tool on an MCP server."""

    async def call_tool(self, name: str, arguments: dict) -> str: ...
