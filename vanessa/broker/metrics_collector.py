"""Periodic broker queue-health metrics.

Refreshes the ``vanessa_broker_stream_length`` / ``vanessa_broker_consumer_lag``
/ ``vanessa_broker_dlq_depth`` gauges so Grafana + Prometheus alerts can watch
for backlog and poison-message accumulation. Runs as a background task in any
process that owns a broker (API, worker, bot).
"""

from __future__ import annotations

import asyncio
import logging

from vanessa.broker.streams import BrokerStreams
from vanessa.observability.metrics import (
    broker_consumer_lag,
    broker_dlq_depth,
    broker_stream_length,
)

logger = logging.getLogger(__name__)


class BrokerMetricsCollector:
    def __init__(
        self,
        broker,
        streams: BrokerStreams,
        *,
        groups: list[tuple[str, str]] | None = None,
        poll_seconds: float = 15.0,
    ) -> None:
        self._broker = broker
        self._streams = streams
        self._groups = groups or []
        self._poll = poll_seconds

    async def update_once(self) -> None:
        for stream in (self._streams.turns, self._streams.tasks):
            length = await self._broker.stream_length(stream)
            broker_stream_length.labels(stream=stream).set(length)
            dlq = f"{stream}:dlq"
            broker_dlq_depth.labels(stream=stream).set(
                await self._broker.stream_length(dlq)
            )
        for stream, group in self._groups:
            broker_consumer_lag.labels(stream=stream, group=group).set(
                await self._broker.consumer_lag(stream, group)
            )

    async def run_forever(self) -> None:
        logger.info("broker_metrics_collector_started poll_seconds=%s", self._poll)
        while True:
            try:
                await self.update_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - metrics must never crash the app
                logger.exception("broker_metrics_update_failed")
            await asyncio.sleep(self._poll)
