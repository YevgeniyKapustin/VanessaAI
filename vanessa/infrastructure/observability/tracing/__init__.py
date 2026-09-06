from __future__ import annotations

import logging
from typing import Any

from langfuse import propagate_attributes

from vanessa.config.settings import settings
from vanessa.infrastructure.observability.tracing.tracing_langfuse import LangfuseTracer
from vanessa.infrastructure.observability.tracing.tracing_sample import (
    hash_identifier,
    should_sample,
)
from vanessa.infrastructure.observability.tracing.tracing_types import (
    NullSpan,
    NullTracer,
    Span,
    Tracer,
)

logger = logging.getLogger(__name__)


def _propagate_attributes(**kwargs: Any) -> Any:
    """Context manager that attaches trace-level attributes (user_id, session_id, ...).

    Uses the Langfuse SDK v4 ``propagate_attributes`` helper. Kept behind a small
    function so tests can swap in a no-op.
    """
    return propagate_attributes(**kwargs)


class _TracerState:
    current: Tracer | None = None


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
    if _TracerState.current is None:
        _TracerState.current = create_tracer()
    return _TracerState.current


def set_tracer(tracer: Tracer | None) -> None:
    """Override the tracer (used by tests)."""
    _TracerState.current = tracer


def reset_tracer() -> None:
    _TracerState.current = None


__all__ = [
    "LangfuseTracer",
    "NullSpan",
    "NullTracer",
    "Span",
    "Tracer",
    "get_tracer",
    "hash_identifier",
    "reset_tracer",
    "set_tracer",
    "should_sample",
]
