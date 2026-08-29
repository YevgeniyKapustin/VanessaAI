"""Run one of the Vanessa MCP servers over Streamable HTTP.

Each server also exposes ``/health`` (liveness) and ``/metrics`` (Prometheus)
next to the MCP endpoint at ``/mcp``.

Usage:
    python -m app.mcp_server.runner websearch --port 8101
    python -m app.mcp_server.runner knowledge --port 8102
    python -m app.mcp_server.runner vision --port 8103
"""

from __future__ import annotations

import argparse

import uvicorn
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from app.mcp_server import knowledge, vision, websearch

_SERVERS = {
    "websearch": websearch.build_server,
    "knowledge": knowledge.build_server,
    "vision": vision.build_server,
}


def build_app(name: str, *, path: str = "/mcp"):
    """Wrap the MCP Streamable-HTTP app with /health and /metrics routes."""
    server = _SERVERS[name]()
    # mcp 1.x sets the HTTP path at construction; point it at the requested one.
    server.streamable_http_path = path
    mcp_app = server.streamable_http_app()

    async def health(_request):
        return JSONResponse({"status": "ok", "server": name})

    async def metrics(_request):
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return Starlette(
        routes=[
            Route("/health", health),
            Route("/metrics", metrics),
            Mount(path, app=mcp_app),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Vanessa MCP server")
    parser.add_argument("server", choices=sorted(_SERVERS))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--path", default="/mcp")
    args = parser.parse_args()

    app = build_app(args.server, path=args.path)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
