from __future__ import annotations

import logging
from uuid import uuid4

from services.agent.broker_worker.handlers import TurnHandlerFactory
from services.agent.container.app import AppContainer
from services.agent.runtime.lifecycle import AsyncRuntime
from services.agent.runtime.tasks import TaskSet
from vanessa.config import settings
from vanessa.infrastructure.db.session import async_session_factory

logger = logging.getLogger(__name__)


class BrokerRuntime(AsyncRuntime):
    def __init__(self, container: AppContainer) -> None:
        self._container = container
        self._tasks = TaskSet()

    async def start(self) -> None:
        from services.agent.broker_worker import BrokerTurnWorker
        from vanessa.infrastructure.broker.metrics_collector import (
            BrokerMetricsCollector,
        )
        from vanessa.infrastructure.broker.streams import BrokerStreams
        from vanessa.infrastructure.outbox.relay import OutboxRelay

        streams = BrokerStreams.from_settings(settings)
        broker = self._container.graph.broker.ensure_client()
        try:
            await broker.ping()
        except Exception as exc:
            raise RuntimeError("broker redis unreachable") from exc
        consumer_suffix = settings.broker_consumer_id or uuid4().hex[:6]
        turn_worker = BrokerTurnWorker(
            broker,
            stream=streams.turns,
            group=settings.broker_group_agent,
            consumer=f"{settings.broker_group_agent}-{consumer_suffix}",
            handlers=TurnHandlerFactory(self._container),
            dedup=broker.dedup_guard(),
        )
        self._tasks.spawn(
            turn_worker.run_forever(),
            name="broker_turn_worker",
            log_stop=True,
        )
        logger.info(
            "broker_turn_worker_started stream=%s group=%s",
            streams.turns,
            settings.broker_group_agent,
        )
        if settings.outbox_enabled:
            outbox_relay = OutboxRelay(
                broker,
                async_session_factory,
                poll_seconds=settings.outbox_poll_seconds,
                batch_size=settings.outbox_batch_size,
                max_attempts=settings.outbox_max_attempts,
            )
            self._tasks.spawn(
                outbox_relay.run_forever(),
                name="outbox_relay",
                log_stop=True,
            )
            logger.info("outbox_relay_started")
        collector = BrokerMetricsCollector(
            broker,
            streams,
            groups=[
                (streams.turns, settings.broker_group_agent),
                (streams.tasks, settings.broker_group_worker),
            ],
            poll_seconds=15.0,
        )
        self._tasks.spawn(
            collector.run_forever(),
            name="broker_metrics",
            log_stop=True,
        )

    async def stop(self) -> None:
        await self._tasks.cancel_all()
        await self._container.graph.broker.close()
