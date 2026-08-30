from typing import Protocol

from fastapi import FastAPI, Request, Response

from vanessa.core.logging_setup import ServiceName


class LoggingSetup(Protocol):
    def __call__(self, service_name: ServiceName) -> None: ...


class HttpCallNext(Protocol):
    async def __call__(self, request: Request) -> Response: ...


class HttpMiddleware(Protocol):
    async def __call__(
        self,
        request: Request,
        call_next: HttpCallNext,
    ) -> Response: ...


class HttpRecorder(Protocol):
    def __call__(
        self,
        *,
        method: str,
        path: str,
        status: int,
        seconds: float,
    ) -> None: ...
