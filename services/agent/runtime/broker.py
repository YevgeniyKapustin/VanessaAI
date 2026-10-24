from __future__ import annotations

import logging
from uuid import uuid4

from services.agent.broker_worker.handlers import TurnHandlerFactory
from services.agent.broker_worker.posted import PostedRecorder
from services.agent.broker_worker.worker import BrokerTurnWorker
from services.agent.container.app import AppContainer
from services.agent.runtime.lifecycle import AsyncRuntime
from services.agent.runtime.tasks import TaskSet
from vanessa.config import settings
from vanessa.infrastructure.broker.metrics_collector import BrokerMetricsCollector
from vanessa.infrastructure.broker.streams import BrokerStreams
from vanessa.infrastructure.db.session import async_session_factory
from vanessa.infrastructure.outbox.relay import OutboxRelay

logger = logging.getLogger(__name__)


def _start_turn_worker(
    tasks: TaskSet,
    container: AppContainer,
    broker,
    streams: BrokerStreams,
) -> None:
    consumer_suffix = settings.broker_consumer_id or uuid4().hex[:6]
    turn_worker = BrokerTurnWorker(
        broker,
        stream=streams.turns,
        group=settings.broker_group_agent,
        consumer=f"{settings.broker_group_agent}-{consumer_suffix}",
        handlers=TurnHandlerFactory(container),
        dedup=broker.dedup_guard(),
        posted=PostedRecorder(
            async_session_factory, container.graph.hermes_answers
        ),
    )
    tasks.spawn(
        turn_worker.run_forever(),
        name="broker_turn_worker",
        log_stop=True,
    )
    logger.info(
        "broker_turn_worker_started stream=%s group=%s",
        streams.turns,
        settings.broker_group_agent,
    )


def _start_outbox(tasks: TaskSet, broker) -> None:
    if not settings.outbox_enabled:
        return
    outbox_relay = OutboxRelay(
        broker,
        async_session_factory,
        poll_seconds=settings.outbox_poll_seconds,
        batch_size=settings.outbox_batch_size,
        max_attempts=settings.outbox_max_attempts,
    )
    tasks.spawn(
        outbox_relay.run_forever(),
        name="outbox_relay",
        log_stop=True,
    )
    logger.info("outbox_relay_started")


def _start_broker_metrics(tasks: TaskSet, broker, streams: BrokerStreams) -> None:
    collector = BrokerMetricsCollector(
        broker,
        streams,
        groups=[
            (streams.turns, settings.broker_group_agent),
            (streams.tasks, settings.broker_group_worker),
        ],
        poll_seconds=15.0,
    )
    tasks.spawn(
        collector.run_forever(),
        name="broker_metrics",
        log_stop=True,
    )


class BrokerRuntime(AsyncRuntime):
    def __init__(self, container: AppContainer) -> None:
        self._container = container
        self._tasks = TaskSet()

    async def start(self) -> None:
        streams = BrokerStreams.from_settings(settings)
        broker = self._container.graph.broker.ensure_client()
        try:
            await broker.ping()
        except Exception as exc:
            raise RuntimeError("broker redis unreachable") from exc
        _start_turn_worker(self._tasks, self._container, broker, streams)
        _start_outbox(self._tasks, broker)
        _start_broker_metrics(self._tasks, broker, streams)

    async def stop(self) -> None:
        await self._tasks.cancel_all()
        await self._container.graph.broker.close()
