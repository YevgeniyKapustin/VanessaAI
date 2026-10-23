import json

import httpx
import pytest

from vanessa.infrastructure.hermes import HermesClient, HermesUnavailableError


def _client(handler) -> HermesClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HermesClient("http://hermes:8642/", "secret", client=http)


async def test_is_online_true_on_health_200():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok"})

    assert await _client(handler).is_online() is True


async def test_is_online_false_when_unreachable():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    assert await _client(handler).is_online() is False


async def test_start_run_sends_session_and_idempotency_key():
    seen: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers["Authorization"]
        seen["key"] = request.headers["Idempotency-Key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(202, json={"run_id": "run_1", "status": "started"})

    run_id = await _client(handler).start_run(
        "open MRs?",
        session_id="telegram-42",
        idempotency_key="turn-7",
        instructions="work only",
    )

    assert run_id == "run_1"
    assert seen["path"] == "/v1/runs"
    assert seen["auth"] == "Bearer secret"
    assert seen["key"] == "turn-7"
    assert seen["body"] == {
        "input": "open MRs?",
        "session_id": "telegram-42",
        "instructions": "work only",
    }


async def test_start_run_without_run_id_raises():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    with pytest.raises(HermesUnavailableError):
        await _client(handler).start_run("q", session_id="s", idempotency_key="k")


async def test_get_run_parses_status_and_output():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/runs/run_1"
        return httpx.Response(200, json={"status": "completed", "output": " Done. "})

    run = await _client(handler).get_run("run_1")

    assert run.status == "completed"
    assert run.output == "Done."
    assert run.is_terminal


async def test_http_error_status_raises_unavailable():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "Too many concurrent runs"})

    with pytest.raises(HermesUnavailableError):
        await _client(handler).get_run("run_1")


async def test_connect_error_raises_unavailable():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(HermesUnavailableError):
        await _client(handler).stop_run("run_1")


async def test_stop_run_accepts_empty_body():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/runs/run_1/stop"
        return httpx.Response(200)

    await _client(handler).stop_run("run_1")
