from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langfuse import Langfuse

from vanessa.config.settings import settings
from vanessa.infrastructure.observability.tracing.tracing_langfuse_trace import (
    _flush_langfuse,
    _null_sampled_span,
    _open_trace,
)
from vanessa.infrastructure.observability.tracing.tracing_sample import (
    _is_sampled,
    _sampled,
    should_sample,
)
from vanessa.infrastructure.observability.tracing.tracing_types import NullSpan, Span

logger = logging.getLogger("vanessa.infrastructure.observability.tracing")


def _build_langfuse_client() -> Any:
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
        flush_interval=settings.langfuse_flush_interval,
    )


class LangfuseTracer:
    """Tracer backed by the Langfuse Python SDK (self-hosted, server v3+/SDK v4)."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client or _build_langfuse_client()

    @property
    def enabled(self) -> bool:
        return True

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
    ) -> AsyncIterator[Span]:
        if not should_sample():
            async with _null_sampled_span() as span:
                yield span
            return
        opened = _open_trace(
            self._client,
            name=name,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
            trace_input=input,
            output=output,
        )
        if opened is None:
            async with _null_sampled_span() as span:
                yield span
            return
        propagator, root = opened
        async with _sampled_observation(propagator, root) as span:
            yield span
        _flush_langfuse(self._client)

    @asynccontextmanager
    async def span(
        self,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
        input: Any = None,  # noqa: A002
        output: Any = None,
    ) -> AsyncIterator[Span]:
        if not _is_sampled():
            yield NullSpan()
            return
        try:
            observation_cm = self._client.start_as_current_observation(
                name=name,
                as_type="span",
                input=input,
                output=output,
                metadata=metadata,
            )
        except Exception:
            logger.warning("langfuse_span_create_failed", exc_info=True)
            yield NullSpan()
            return
        with observation_cm as observation:
            yield _LangfuseSpan(observation)

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
    ) -> AsyncIterator[Span]:
        if not _is_sampled():
            yield NullSpan()
            return
        try:
            observation_cm = self._client.start_as_current_observation(
                name=name,
                as_type="generation",
                model=model,
                input=input,
                output=output,
                usage_details=usage,
                metadata=metadata,
            )
        except Exception:
            logger.warning("langfuse_generation_create_failed", exc_info=True)
            yield NullSpan()
            return
        with observation_cm as observation:
            yield _LangfuseSpan(observation)


class _LangfuseSpan:
    """Thin adapter exposing ``update`` on a Langfuse v4 span/generation object."""

    __slots__ = ("_observation",)

    def __init__(self, observation: Any) -> None:
        self._observation = observation

    def update(self, **kwargs: Any) -> None:
        # Callers pass the v2-era ``usage=``; SDK v4 expects ``usage_details=``.
        try:
            if "usage" in kwargs:
                usage = kwargs.pop("usage")
                if usage is not None:
                    kwargs["usage_details"] = usage
            self._observation.update(**kwargs)
        except Exception:
            logger.warning("langfuse_observation_update_failed", exc_info=True)


@asynccontextmanager
async def _sampled_observation(propagator: Any, root: Any) -> AsyncIterator[Span]:
    with propagator, root as observation:
        sample_token = _sampled.set(True)
        try:
            yield _LangfuseSpan(observation)
        finally:
            _sampled.reset(sample_token)
