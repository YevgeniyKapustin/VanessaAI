"""Shared consumer plumbing for stream backends.

``consume_forever`` implements the delivery loop exactly once: read → dedup →
handle → ack; a failing handler moves the message to the dead-letter stream.
Concrete backends (Redis Streams, in-memory) only implement the small
``StreamBackend`` protocol.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from vanessa.contracts.messages import BrokerMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Delivery:
    """A message handed to a consumer together with its stream position."""

    stream: str
    stream_id: str
    message: BrokerMessage


MessageHandler = Callable[[Delivery], Awaitable[None]]


class DedupGuard(Protocol):
    """Remembers processed message ids so redeliveries are skipped."""

    async def acquire(self, message_id: str) -> bool:
        """Return True if ``message_id`` was NOT seen before (first delivery)."""
        ...


class StreamBackend(Protocol):
    """Minimal read/ack/reject interface a stream transport must provide."""

    async def ensure_group(self, stream: str, group: str) -> None: ...

    async def read(
        self, *, stream: str, group: str, consumer: str, count: int
    ) -> list[Delivery]: ...

    async def ack(self, stream: str, group: str, stream_id: str) -> None: ...

    async def reject(
        self, stream: str, group: str, delivery: Delivery, error: BaseException
    ) -> None: ...


async def consume_forever(
    backend: StreamBackend,
    *,
    stream: str,
    group: str,
    consumer: str,
    handler: MessageHandler,
    dedup: DedupGuard | None = None,
    poll_seconds: float = 0.05,
    count: int = 1,
) -> None:
    """Polling delivery loop: read → dedup → handle → ack, DLQ on failure.

    Reads are non-blocking and paced by ``poll_seconds`` so the loop never
    hogs the event loop and behaves identically against real Redis and
    in-memory test doubles.
    """
    await backend.ensure_group(stream, group)
    while True:
        deliveries = await backend.read(
            stream=stream, group=group, consumer=consumer, count=count
        )
        for delivery in deliveries:
            await _process_one(backend, group, delivery, handler, dedup)
        if not deliveries:
            await asyncio.sleep(poll_seconds)


async def _already_handled(dedup: DedupGuard, delivery: Delivery) -> bool:
    try:
        return not await dedup.acquire(delivery.message.message_id)
    except Exception:
        logger.exception(
            "dedup_lookup_failed stream=%s id=%s",
            delivery.stream,
            delivery.stream_id,
        )
        return True


async def _should_skip_delivery(
    delivery: Delivery,
    dedup: DedupGuard | None,
) -> bool:
    if dedup is None:
        return False
    return await _already_handled(dedup, delivery)


async def _reject_delivery(
    backend: StreamBackend,
    group: str,
    delivery: Delivery,
    exc: BaseException,
) -> None:
    try:
        await backend.reject(delivery.stream, group, delivery, exc)
    except Exception:
        logger.exception(
            "broker_reject_failed stream=%s id=%s",
            delivery.stream,
            delivery.stream_id,
        )


async def _run_handler(
    backend: StreamBackend,
    group: str,
    delivery: Delivery,
    handler: MessageHandler,
) -> None:
    try:
        await handler(delivery)
        await backend.ack(delivery.stream, group, delivery.stream_id)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception(
            "consumer_handler_failed stream=%s id=%s",
            delivery.stream,
            delivery.stream_id,
        )
        await _reject_delivery(backend, group, delivery, exc)


async def _process_one(
    backend: StreamBackend,
    group: str,
    delivery: Delivery,
    handler: MessageHandler,
    dedup: DedupGuard | None,
) -> None:
    if await _should_skip_delivery(delivery, dedup):
        # Duplicate or failed dedup lookup: ack and skip the handler.
        await backend.ack(delivery.stream, group, delivery.stream_id)
        return
    await _run_handler(backend, group, delivery, handler)
