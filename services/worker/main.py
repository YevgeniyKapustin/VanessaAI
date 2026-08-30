"""Background worker entrypoint.

Runs in its own container (isolated CPU/RAM): consumes ``TaskMessage``s from
the broker's task stream and runs the heavy handlers, plus the sweep/portrait
polling loops.

    python -m services.worker.main
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from uuid import uuid4

from services.worker.app import WorkerApp
from services.worker.handlers import build_worker_handlers
from vanessa.config import settings
from vanessa.core.logging_setup import configure_logging
from vanessa.infrastructure.broker.redis_streams import RedisStreamBroker
from vanessa.infrastructure.broker.streams import BrokerStreams
from vanessa.infrastructure.db.session import async_session_factory
from vanessa.knowledge.portraits import PortraitWorker
from vanessa.knowledge.sweep import SweepWorker

configure_logging("worker")
logger = logging.getLogger(__name__)


async def main() -> None:
    from vanessa.infrastructure.observability.metrics import start_metrics_http_server

    start_metrics_http_server(settings.worker_metrics_port)
    logger.info(
        "worker health/metrics endpoint started on :%s",
        settings.worker_metrics_port,
    )

    streams = BrokerStreams.from_settings(settings)
    broker = RedisStreamBroker(
        settings.broker_redis_url,
        stream_maxlen=settings.broker_stream_maxlen,
        dlq_enabled=settings.broker_dlq_enabled,
    )
    from vanessa.infrastructure.broker.metrics_collector import BrokerMetricsCollector

    broker_metrics = BrokerMetricsCollector(
        broker,
        streams,
        groups=[
            (streams.turns, settings.broker_group_agent_core),
            (streams.tasks, settings.broker_group_worker),
        ],
        poll_seconds=15.0,
    )
    metrics_task = asyncio.create_task(broker_metrics.run_forever())
    assembly = await build_worker_handlers()
    consumer_suffix = settings.broker_consumer_id or uuid4().hex[:6]
    # The polling loops only run when the deployment is explicitly in worker
    # mode — otherwise the API process still owns them and starting them here
    # too would duplicate the work. Task consumption runs regardless.
    sweep_worker = (
        SweepWorker(
            assembly.sweep,
            async_session_factory,
            poll_seconds=settings.knowledge_sweep_poll_seconds,
        )
        if (
            assembly.sweep is not None
            and settings.knowledge_sweep_enabled
            and settings.worker_enabled
        )
        else None
    )
    portrait_worker = (
        PortraitWorker(
            assembly.portrait,
            poll_seconds=settings.knowledge_portrait_poll_seconds,
        )
        if (
            assembly.portrait is not None
            and settings.knowledge_portrait_enabled
            and settings.worker_enabled
        )
        else None
    )
    app = WorkerApp(
        broker,
        assembly.handlers,
        tasks_stream=streams.tasks,
        group=settings.broker_group_worker,
        consumer=f"{settings.broker_group_worker}-{consumer_suffix}",
        dedup=broker.dedup_guard(),
        sweep_worker=sweep_worker,
        portrait_worker=portrait_worker,
    )
    logger.info("worker_started stream=%s group=%s", streams.tasks, settings.broker_group_worker)
    try:
        await app.run_forever()
    finally:
        metrics_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await metrics_task
        await broker.close()


if __name__ == "__main__":
    asyncio.run(main())
