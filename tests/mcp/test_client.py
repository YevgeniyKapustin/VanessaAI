import json
import socket
import threading

import pytest
import uvicorn

from vanessa.core.messages import WebResult
from vanessa.infrastructure.mcp.circuit_breaker import CircuitBreaker
from vanessa.infrastructure.mcp.client import FailOpenMcpClient
from vanessa.infrastructure.mcp.websearch import McpWebSearch


class _FakeClient:
    def __init__(self, result="[]", error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, arguments: dict) -> str:
        self.calls.append((name, arguments))
        if self._error is not None:
            raise self._error
        return self._result


# --- FailOpenMcpClient ---------------------------------------------------------

async def test_fail_open_returns_fallback_on_error() -> None:
    client = FailOpenMcpClient(
        _FakeClient(error=RuntimeError("server down")),
        fail_open=True,
        fallback="[]",
    )
    result = await client.call_tool("web_search", {"query": "x"})
    assert result == "[]"


async def test_fail_open_raises_when_not_fail_open() -> None:
    client = FailOpenMcpClient(
        _FakeClient(error=RuntimeError("server down")),
        fail_open=False,
    )
    with pytest.raises(RuntimeError):
        await client.call_tool("web_search", {"query": "x"})


async def test_fail_open_trips_circuit_after_repeated_failures() -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=60)
    inner = _FakeClient(error=RuntimeError("down"))
    client = FailOpenMcpClient(inner, breaker=breaker, fail_open=True, fallback="[]")
    for _ in range(2):
        await client.call_tool("web_search", {"query": "x"})
    assert breaker.state == "open"
    # Breaker is open → request short-circuits without touching the inner client.
    before = len(inner.calls)
    await client.call_tool("web_search", {"query": "x"})
    assert len(inner.calls) == before


async def test_success_resets_circuit() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=30)
    client = FailOpenMcpClient(_FakeClient(), breaker=breaker)
    await client.call_tool("web_search", {"query": "x"})
    assert breaker.state == "closed"


# --- CircuitBreaker ------------------------------------------------------------

def test_circuit_breaker_trips_and_half_open_allows_probe() -> None:
    import time

    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=30)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == "open"
    assert breaker.allow_request() is False
    # Simulate the reset timeout elapsing → half-open → one probe allowed.
    breaker._open_since = time.monotonic() - 31
    assert breaker.state == "half_open"
    assert breaker.allow_request() is True
    breaker.record_success()
    assert breaker.state == "closed"


# --- McpWebSearch adapter ------------------------------------------------------

async def test_mcp_web_search_parses_results() -> None:
    payload = json.dumps(
        [
            {
                "title": "A",
                "url": "https://a.example",
                "snippet": "hello",
                "published_date": "2026-01-01",
            }
        ]
    )
    fake = _FakeClient(result=payload)
    search = McpWebSearch(fake, max_results=5)
    results = await search.search("ванесса", limit=5)
    assert results == [
        WebResult(title="A", url="https://a.example", snippet="hello", published_date="2026-01-01")
    ]
    assert fake.calls == [("web_search", {"query": "ванесса", "limit": 5})]


async def test_mcp_web_search_unparseable_returns_empty() -> None:
    search = McpWebSearch(_FakeClient(result="not json"), max_results=5)
    assert await search.search("x") == []


# --- Live HTTP round-trip (real MCP server ↔ real client) ----------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_port(port: int, timeout: float = 10.0) -> None:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as s:
            s.settimeout(0.25)
            try:
                s.connect(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.05)
    raise RuntimeError(f"port {port} never became ready")


async def test_streamable_http_client_round_trip() -> None:
    from services.mcp import websearch
    from vanessa.core.messages import WebResult
    from vanessa.infrastructure.mcp.client import StreamableHttpMcpClient

    class _Provider:
        async def search(self, query, *, limit=5):
            return [
                WebResult(
                    title="Title",
                    url="https://example.com",
                    snippet="Snippet",
                    published_date="2026-01-01",
                )
            ]

    server = websearch.build_server(provider=_Provider())
    server.streamable_http_path = "/mcp"
    app = server.streamable_http_app()
    port = _free_port()
    holder: dict = {}

    def run() -> None:
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        holder["server"] = uvicorn.Server(config)
        holder["server"].run()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    _wait_port(port)
    try:
        client = StreamableHttpMcpClient(f"http://127.0.0.1:{port}/mcp", timeout=10)
        raw = await client.call_tool("web_search", {"query": "vanessa", "limit": 5})
        data = json.loads(raw)
        assert data[0]["title"] == "Title"
        assert data[0]["url"] == "https://example.com"
    finally:
        if "server" in holder:
            holder["server"].should_exit = True
            thread.join(timeout=5)
