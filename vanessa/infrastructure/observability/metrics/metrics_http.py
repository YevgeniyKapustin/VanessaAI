from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from vanessa.config.settings import settings
from vanessa.infrastructure.observability.metrics.metrics_io import (
    _refresh_activity_gauges,
)
from vanessa.infrastructure.observability.metrics.metrics_pipeline import registry


def render_metrics() -> bytes:
    """Prometheus text exposition for GET /metrics (activity gauges refreshed)."""
    _refresh_activity_gauges()
    return generate_latest(registry)


def metrics_token_allowed(headers: Mapping[str, str]) -> bool:
    """True when /metrics may be served for these request headers."""
    if not settings.metrics_require_token:
        return True
    expected = settings.api_internal_token.strip()
    if not expected:
        return True
    header = str(headers.get("X-Internal-Token") or "").strip()
    auth = str(headers.get("Authorization") or "")
    bearer = ""
    if auth.lower().startswith("bearer "):
        bearer = auth[7:].strip()
    return expected in (header, bearer)


class ProcessMetricsServer(ThreadingHTTPServer):
    ready_check: Callable[[], bool] | None = None


class _ProcessHttpHandler(BaseHTTPRequestHandler):
    """Serve /health for probes and /metrics for Prometheus."""

    server: ProcessMetricsServer

    def log_message(self, fmt: str, *args: object) -> None:
        del fmt, args

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/health", "/health/live"):
            self._plain(200, b"ok\n")
            return
        if path == "/health/ready":
            self._ready()
            return
        if path == "/metrics":
            self._metrics()
            return
        self._plain(404, b"not found\n")

    def _ready(self) -> None:
        check = self.server.ready_check
        if check is not None and not check():
            self._plain(503, b"unavailable\n")
            return
        self._plain(200, b"ok\n")

    def _metrics(self) -> None:
        if not metrics_token_allowed(self.headers):
            self._plain(401, b"unauthorized\n")
            return
        body = render_metrics() if settings.metrics_enabled else b"# metrics disabled\n"
        self._send(200, body, CONTENT_TYPE_LATEST)

    def _plain(self, status: int, body: bytes) -> None:
        self._send(status, body, "text/plain; charset=utf-8")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_metrics_http_server(
    port: int,
    addr: str = "0.0.0.0",
    ready_check: Callable[[], bool] | None = None,
) -> ProcessMetricsServer:
    """Always serve /health. /metrics is empty when metrics are off."""
    server = ProcessMetricsServer((addr, int(port)), _ProcessHttpHandler)
    server.ready_check = ready_check
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
