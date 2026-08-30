"""Standalone MCP servers exposing Vanessa's external capabilities.

Each ``build_server()`` returns a ``MCPServer`` (MCP 2.x) that can run over
Streamable HTTP/SSE. The agent core talks to these over the wire — never by
importing them. Servers are isolated processes/containers with their own
resource limits.
"""
