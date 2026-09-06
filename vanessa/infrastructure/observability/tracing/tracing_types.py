from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Protocol


class Span(Protocol):
    """A traceable unit (span or generation) yielded to the caller."""

    def update(self, **kwargs: Any) -> None: ...


class NullSpan:
    """No-op span used when tracing is disabled or a turn is not sampled."""

    def update(self, **kwargs: Any) -> None:
        del kwargs


class Tracer(Protocol):
    """Minimal tracing interface the application depends on."""

    @property
    def enabled(self) -> bool: ...

    def trace(
        self,
        *,
        name: str,
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        input: Any = None,  # noqa: A002
        output: Any = None,
    ) -> AsyncIterator[Span]: ...

    def span(
        self,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
        input: Any = None,  # noqa: A002
        output: Any = None,
    ) -> AsyncIterator[Span]: ...

    def generation(
        self,
        *,
        name: str,
        model: str | None = None,
        input: Any = None,  # noqa: A002
        output: Any = None,
        usage: dict[str, int] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[Span]: ...


class NullTracer:
    """Tracer that does nothing; used when tracing is disabled."""

    enabled = False

    @asynccontextmanager
    async def trace(
        self,
        *,
        name: str,
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        input: Any = None,  # noqa: A002
        output: Any = None,
    ) -> AsyncIterator[NullSpan]:
        del name, user_id, session_id, metadata, input, output
        yield NullSpan()

    @asynccontextmanager
    async def span(
        self,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
        input: Any = None,  # noqa: A002
        output: Any = None,
    ) -> AsyncIterator[NullSpan]:
        del name, metadata, input, output
        yield NullSpan()

    @asynccontextmanager
    async def generation(
        self,
        *,
        name: str,
        model: str | None = None,
        input: Any = None,  # noqa: A002
        output: Any = None,
        usage: dict[str, int] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[NullSpan]:
        del name, model, input, output, usage, metadata
        yield NullSpan()
