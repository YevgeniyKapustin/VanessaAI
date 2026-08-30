from contextvars import ContextVar
from typing import ClassVar

from fastapi import Request, Response

from services.agent.protocols import HttpCallNext
from vanessa.core.request_context import new_request_id, request_id_var


class RequestIdMiddleware:
    header: ClassVar[str] = "X-Request-ID"

    def __init__(self, request_ids: ContextVar[str] | None = None) -> None:
        self._request_ids = request_ids or request_id_var

    async def __call__(self, request: Request, call_next: HttpCallNext) -> Response:
        token = self._request_ids.set(self._incoming_id(request))
        try:
            response = await call_next(request)
            response.headers[self.header] = self._request_ids.get()
            return response
        finally:
            self._request_ids.reset(token)

    def _incoming_id(self, request: Request) -> str:
        return request.headers.get(self.header) or new_request_id()
