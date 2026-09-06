from __future__ import annotations

import hashlib
import random
from contextvars import ContextVar

from vanessa.config.settings import settings

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
