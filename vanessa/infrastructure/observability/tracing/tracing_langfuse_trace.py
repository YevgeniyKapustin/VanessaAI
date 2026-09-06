from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langfuse.types import TraceContext

from vanessa.infrastructure.observability.tracing.tracing_sample import _sampled
from vanessa.infrastructure.observability.tracing.tracing_types import NullSpan, Span

logger = logging.getLogger("vanessa.infrastructure.observability.tracing")


def _propagate_attributes(**kwargs: Any) -> Any:
    tracing_mod = sys.modules["vanessa.infrastructure.observability.tracing"]
    return tracing_mod._propagate_attributes(**kwargs)


def _trace_attrs(
    name: str, user_id: str | None, session_id: str | None
) -> dict[str, Any]:
    attrs: dict[str, Any] = {"trace_name": name}
    if user_id is not None:
        attrs["user_id"] = user_id
    if session_id is not None:
        attrs["session_id"] = session_id
    return attrs


@asynccontextmanager
async def _null_sampled_span() -> AsyncIterator[Span]:
    sample_token = _sampled.set(False)
    try:
        yield NullSpan()
    finally:
        _sampled.reset(sample_token)


def _open_trace(
    client: Any,
    *,
    name: str,
    user_id: str | None,
    session_id: str | None,
    metadata: dict[str, Any] | None,
    trace_input: Any,
    output: Any,
) -> tuple[Any, Any] | None:
    try:
        trace_id = client.create_trace_id()
        propagator = _propagate_attributes(
            **_trace_attrs(name, user_id, session_id)
        )
        root = client.start_as_current_observation(
            trace_context=TraceContext(trace_id=trace_id),
            name=name,
            as_type="chain",
            input=trace_input,
            output=output,
            metadata=metadata or {},
        )
    except Exception:
        logger.warning("langfuse_trace_setup_failed", exc_info=True)
        return None
    return propagator, root


def _flush_langfuse(client: Any) -> None:
    try:
        client.flush()
    except Exception:
        logger.warning("langfuse_flush_failed", exc_info=True)
