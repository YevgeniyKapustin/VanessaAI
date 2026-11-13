"""Retrying transport calls for the consumer loop.

A broker transport error must not end the delivery loop: the process would
keep answering health probes while nobody reads the stream. Every call here
swallows transport failures, backs off and returns so the loop keeps going.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vanessa.infrastructure.broker.backends import Delivery, StreamBackend

logger = logging.getLogger(__name__)

_MAX_BACKOFF_SECONDS = 5.0
_BACKOFF_STEP_SECONDS = 0.5


def backoff_delay(failures: int) -> float:
    """Linear backoff capped at ``_MAX_BACKOFF_SECONDS``."""
    return min(_MAX_BACKOFF_SECONDS, _BACKOFF_STEP_SECONDS * failures)


async def _backoff(op: str, exc: BaseException, failures: int) -> None:
    delay = backoff_delay(failures)
    logger.warning(
        "broker_transport_failed op=%s failures=%s retry_in=%.1fs error=%r",
        op,
        failures,
        delay,
        exc,
    )
    await asyncio.sleep(delay)


async def ensure_group_retrying(
    backend: StreamBackend, *, stream: str, group: str
) -> None:
    """Create the consumer group, retrying while the transport is down."""
    failures = 0
    while True:
        try:
            await backend.ensure_group(stream, group)
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - any transport error is retryable
            failures += 1
            await _backoff(f"ensure_group:{stream}", exc, failures)


async def read_retrying(
    backend: StreamBackend,
    *,
    stream: str,
    group: str,
    consumer: str,
    count: int,
    failures: int,
) -> tuple[list[Delivery], int]:
    """Read one batch; on a transport error return no deliveries and back off."""
    try:
        deliveries = await backend.read(
            stream=stream, group=group, consumer=consumer, count=count
        )
        return deliveries, 0
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - any transport error is retryable
        failed_so_far = failures + 1
        await _backoff(f"read:{stream}", exc, failed_so_far)
        return [], failed_so_far
