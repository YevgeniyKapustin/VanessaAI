import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from vanessa.core.request_context import get_request_id, new_request_id, request_id_var
from vanessa.observability.metrics import record_http


def register_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or new_request_id()
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = get_request_id()
            record_http(
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                seconds=time.perf_counter() - started,
            )
            return response
        finally:
            request_id_var.reset(token)
