"""Agent-core MCP client: wire protocol + fail-open tool invocation."""

from vanessa.infrastructure.mcp.circuit_breaker import CircuitBreaker
from vanessa.infrastructure.mcp.client import FailOpenMcpClient, StreamableHttpMcpClient
from vanessa.infrastructure.mcp.protocols import McpClientProtocol
from vanessa.infrastructure.mcp.websearch import McpWebSearch

__all__ = [
    "CircuitBreaker",
    "FailOpenMcpClient",
    "StreamableHttpMcpClient",
    "McpClientProtocol",
    "McpWebSearch",
]
