"""Liveness registry for broker consumer loops.

The HTTP probe only proves the process is up, so a consumer loop that died
leaves the container "healthy" while nobody reads the stream — the owner sees
a bot that stopped answering. Every ``consume_forever`` registers its own task
here and the readiness probe fails while a registered consumer is finished.
"""

from __future__ import annotations

import asyncio

_CONSUMERS: dict[str, asyncio.Task] = {}


def consumer_key(*, group: str, stream: str) -> str:
    return f"consume:{group}:{stream}"


def watch(name: str, task: asyncio.Task | None) -> None:
    """Register ``task`` as consumer ``name``; a restart overwrites it."""
    if task is not None:
        _CONSUMERS[name] = task


def unwatch(name: str) -> None:
    _CONSUMERS.pop(name, None)


def dead_consumers() -> list[str]:
    """Names of registered consumers whose loop task has finished."""
    return [name for name, task in list(_CONSUMERS.items()) if task.done()]
