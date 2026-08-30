from unittest.mock import MagicMock
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from services.agent.main import postgres_ready
from vanessa.infrastructure.observability.metrics import start_metrics_http_server


def test_health_and_live_ok() -> None:
    server = start_metrics_http_server(0, addr="127.0.0.1")
    try:
        host, port = server.server_address
        for path in ("/health", "/health/live", "/health/ready"):
            with urlopen(f"http://{host}:{port}{path}", timeout=2) as response:
                assert response.status == 200
                assert response.read() == b"ok\n"
    finally:
        server.shutdown()
        server.server_close()


def test_readiness_unavailable_when_check_fails() -> None:
    server = start_metrics_http_server(
        0, addr="127.0.0.1", ready_check=lambda: False
    )
    try:
        host, port = server.server_address
        with pytest.raises(HTTPError) as caught:
            urlopen(f"http://{host}:{port}/health/ready", timeout=2)
        assert caught.value.code == 503
        with urlopen(f"http://{host}:{port}/health", timeout=2) as response:
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()


def test_postgres_ready_false_on_error(monkeypatch) -> None:
    engine = MagicMock()
    engine.sync_engine.connect.side_effect = RuntimeError("db down")
    monkeypatch.setattr("services.agent.main.engine", engine)
    assert postgres_ready() is False
