from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from vanessa.config import settings
from vanessa.infrastructure.observability.metrics import (
    record_turn,
    start_metrics_http_server,
)


@pytest.fixture
def metrics_server(monkeypatch):
    monkeypatch.setattr(settings, "metrics_enabled", True)
    monkeypatch.setattr(settings, "metrics_require_token", False)
    server = start_metrics_http_server(0, addr="127.0.0.1")
    yield server
    server.shutdown()
    server.server_close()


def test_prometheus_metrics_endpoint(metrics_server) -> None:
    record_turn("reply", "intent")
    host, port = metrics_server.server_address
    with urlopen(f"http://{host}:{port}/metrics", timeout=2) as response:
        assert response.status == 200
        assert "text/plain" in response.headers["content-type"]
        body = response.read().decode()
        assert "vanessa_turns_total" in body


def test_prometheus_metrics_endpoint_requires_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, "metrics_enabled", True)
    monkeypatch.setattr(settings, "metrics_require_token", True)
    monkeypatch.setattr(settings, "api_internal_token", "secret")
    server = start_metrics_http_server(0, addr="127.0.0.1")
    try:
        host, port = server.server_address
        with pytest.raises(HTTPError) as denied:
            urlopen(f"http://{host}:{port}/metrics", timeout=2)
        assert denied.value.code == 401
        allowed = Request(
            f"http://{host}:{port}/metrics",
            headers={"X-Internal-Token": "secret"},
        )
        with urlopen(allowed, timeout=2) as response:
            assert response.status == 200
        bearer = Request(
            f"http://{host}:{port}/metrics",
            headers={"Authorization": "Bearer secret"},
        )
        with urlopen(bearer, timeout=2) as response:
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()
