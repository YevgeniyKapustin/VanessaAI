from collections.abc import Sequence

from fastapi import FastAPI

from services.agent.middleware.auth import InternalTokenAuth, internal_token_auth
from services.agent.middleware.http_metrics import HttpMetricsMiddleware
from services.agent.middleware.request_id import RequestIdMiddleware
from services.agent.protocols import HttpMiddleware


def default_middleware() -> tuple[HttpMiddleware, ...]:
    return (RequestIdMiddleware(), HttpMetricsMiddleware())


def register_middleware(
    app: FastAPI,
    middleware: Sequence[HttpMiddleware] | None = None,
) -> None:
    stack = default_middleware() if middleware is None else middleware
    for item in reversed(tuple(stack)):
        app.middleware("http")(item)


__all__ = [
    "HttpMetricsMiddleware",
    "InternalTokenAuth",
    "RequestIdMiddleware",
    "default_middleware",
    "internal_token_auth",
    "register_middleware",
]
