from time import perf_counter

from fastapi import Request, Response
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from services.agent.protocols import HttpCallNext, HttpRecorder
from vanessa.infrastructure.observability.metrics import record_http


class HttpMetricsMiddleware:
    def __init__(self, recorder: HttpRecorder | None = None) -> None:
        self._recorder = recorder or record_http

    async def __call__(self, request: Request, call_next: HttpCallNext) -> Response:
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            self._record(request, HTTP_500_INTERNAL_SERVER_ERROR, started)
            raise
        self._record(request, response.status_code, started)
        return response

    def _record(self, request: Request, status: int, started: float) -> None:
        self._recorder(
            method=request.method,
            path=request.url.path,
            status=status,
            seconds=perf_counter() - started,
        )
