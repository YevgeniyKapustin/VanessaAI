"""Agent-core MCP client: wire protocol + fail-open tool invocation."""

from vanessa.mcp.circuit_breaker import CircuitBreaker
from vanessa.mcp.client import FailOpenMcpClient, StreamableHttpMcpClient
from vanessa.mcp.protocols import McpClientProtocol
from vanessa.mcp.websearch import McpWebSearch

__all__ = [
    "CircuitBreaker",
    "FailOpenMcpClient",
    "StreamableHttpMcpClient",
    "McpClientProtocol",
    "McpWebSearch",
]
