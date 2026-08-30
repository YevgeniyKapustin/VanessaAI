from contextvars import ContextVar
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from starlette.responses import Response
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from services.agent.middleware import register_middleware
from services.agent.middleware.auth import InternalTokenAuth
from services.agent.middleware.http_metrics import HttpMetricsMiddleware
from services.agent.middleware.request_id import RequestIdMiddleware


def test_register_adds_outermost_last() -> None:
    app = MagicMock()
    added: list[object] = []

    def capture(_kind: str):
        def add(instance: object) -> None:
            added.append(instance)

        return add

    app.middleware = capture
    outer, inner = MagicMock(), MagicMock()
    register_middleware(app, (outer, inner))
    assert added == [inner, outer]


@pytest.mark.asyncio
async def test_request_id_uses_header_and_custom_context() -> None:
    custom = ContextVar("test_request_id", default="-")
    request = MagicMock()
    request.headers.get.return_value = "trace-1"

    async def call_next(_request: object) -> Response:
        assert custom.get() == "trace-1"
        return Response(status_code=200)

    response = await RequestIdMiddleware(request_ids=custom)(request, call_next)
    assert response.headers[RequestIdMiddleware.header] == "trace-1"
    assert custom.get() == "-"


@pytest.mark.asyncio
async def test_metrics_records_500_on_unhandled_error() -> None:
    recorded: list[dict] = []
    request = MagicMock()
    request.method = "GET"
    request.url.path = "/boom"

    async def boom(_request: object) -> None:
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError, match="fail"):
        await HttpMetricsMiddleware(recorder=lambda **kw: recorded.append(kw))(
            request,
            boom,
        )

    assert recorded[0]["status"] == HTTP_500_INTERNAL_SERVER_ERROR
    assert recorded[0]["method"] == "GET"
    assert recorded[0]["path"] == "/boom"


@pytest.mark.asyncio
async def test_internal_token_skips_when_empty() -> None:
    await InternalTokenAuth(expected="")(x_internal_token=None)


@pytest.mark.asyncio
async def test_internal_token_rejects_mismatch() -> None:
    with pytest.raises(HTTPException) as caught:
        await InternalTokenAuth(expected="secret")(x_internal_token="nope")
    assert caught.value.status_code == 401


@pytest.mark.asyncio
async def test_internal_token_accepts_match() -> None:
    await InternalTokenAuth(expected="secret")(x_internal_token="secret")

