from __future__ import annotations

import hashlib
import logging
import random
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, AsyncIterator, Protocol

from vanessa.config.settings import settings

logger = logging.getLogger(__name__)

# Whether the current turn was sampled for tracing. Providers/stages check it
# before creating a span so unsampled turns emit nothing (no orphan spans).
_sampled: ContextVar[bool] = ContextVar("langfuse_sampled", default=True)


def _is_sampled() -> bool:
    return _sampled.get()


def hash_identifier(value: str | int | None, salt: str | None = None) -> str:
    """Stable, non-reversible hash of a user/chat id (privacy for traces/logs)."""
    if value is None:
        return "anonymous"
    raw = f"{value}:{salt or settings.langfuse_id_salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def should_sample() -> bool:
    """Whether a new turn should be traced, based on LANGFUSE_SAMPLE_RATE."""
    rate = settings.langfuse_sample_rate
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() < rate


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
        input: Any = None,
        output: Any = None,
    ) -> AsyncIterator[Span]: ...

    def span(
        self,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
        input: Any = None,
        output: Any = None,
    ) -> AsyncIterator[Span]: ...

    def generation(
        self,
        *,
        name: str,
        model: str | None = None,
        input: Any = None,
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
        input: Any = None,
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
        input: Any = None,
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
        input: Any = None,
        output: Any = None,
        usage: dict[str, int] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[NullSpan]:
        del name, model, input, output, usage, metadata
        yield NullSpan()


def _propagate_attributes(**kwargs: Any) -> Any:
    """Context manager that attaches trace-level attributes (user_id, session_id, ...).

    Uses the Langfuse SDK v4 ``propagate_attributes`` helper. Imported lazily so this
    module imports cleanly without the SDK (the NullTracer path). Kept behind a small
    function so tests can swap in a no-op.
    """
    from langfuse import propagate_attributes

    return propagate_attributes(**kwargs)


class LangfuseTracer:
    """Tracer backed by the Langfuse Python SDK (self-hosted, server v3+/SDK v4)."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client or self._build_client()

    @staticmethod
    def _build_client() -> Any:
        from langfuse import Langfuse

        return Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            flush_interval=settings.langfuse_flush_interval,
        )

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
        input: Any = None,
        output: Any = None,
    ) -> AsyncIterator[Span]:
        if not should_sample():
            sample_token = _sampled.set(False)
            try:
                yield NullSpan()
            finally:
                _sampled.reset(sample_token)
            return
        try:
            from langfuse.types import TraceContext

            trace_id = self._client.create_trace_id()
            attrs: dict[str, Any] = {"trace_name": name}
            if user_id is not None:
                attrs["user_id"] = user_id
            if session_id is not None:
                attrs["session_id"] = session_id
            propagator = _propagate_attributes(**attrs)
            root = self._client.start_as_current_observation(
                trace_context=TraceContext(trace_id=trace_id),
                name=name,
                as_type="chain",
                input=input,
                output=output,
                metadata=metadata or {},
            )
        except Exception:
            logger.warning("langfuse_trace_setup_failed", exc_info=True)
            sample_token = _sampled.set(False)
            try:
                yield NullSpan()
            finally:
                _sampled.reset(sample_token)
            return
        with propagator:
            with root as observation:
                sample_token = _sampled.set(True)
                try:
                    yield _LangfuseSpan(observation)
                finally:
                    _sampled.reset(sample_token)
        try:
            self._client.flush()
        except Exception:
            logger.warning("langfuse_flush_failed", exc_info=True)

    @asynccontextmanager
    async def span(
        self,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
        input: Any = None,
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
        input: Any = None,
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


_tracer: Tracer | None = None


def create_tracer() -> Tracer:
    """Build the process-wide tracer from settings (NullTracer when disabled)."""
    if not settings.langfuse_enabled:
        return NullTracer()
    try:
        return LangfuseTracer()
    except Exception:
        logger.exception("failed to initialize Langfuse tracer, using NullTracer")
        return NullTracer()


def get_tracer() -> Tracer:
    global _tracer
    if _tracer is None:
        _tracer = create_tracer()
    return _tracer


def set_tracer(tracer: Tracer | None) -> None:
    """Override the tracer (used by tests)."""
    global _tracer
    _tracer = tracer


def reset_tracer() -> None:
    global _tracer
    _tracer = None


__all__ = [
    "Span",
    "Tracer",
    "NullSpan",
    "NullTracer",
    "LangfuseTracer",
    "hash_identifier",
    "should_sample",
    "get_tracer",
    "set_tracer",
    "reset_tracer",
]
