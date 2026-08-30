from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI

from services.agent_core.container import get_app_container
from services.agent_core.deps import create_embedding_provider, create_vector_store
from services.agent_core.middleware import register_request_id_middleware
from services.agent_core.routes import chat, health, metrics, notes, observability
from vanessa.config import settings
from vanessa.core.logging_setup import configure_logging
from vanessa.infrastructure.observability.alerting import create_alert_manager
from vanessa.infrastructure.db.base import Base
from vanessa.infrastructure.db.session import async_session_factory, engine
from vanessa.knowledge.compaction import compact_all_person_cards
from vanessa.knowledge.index import KnowledgeIndex
from vanessa.knowledge.memory_planner import MemoryPlanner
from vanessa.knowledge.metrics.deterministic import DeterministicMetricsCalculator
from vanessa.knowledge.metrics.pipeline import MetricsPipeline
from vanessa.knowledge.metrics.planner import MetricsPlanner
from vanessa.knowledge.metrics.store import MetricsStore
from vanessa.knowledge.portraits import PortraitBuilder, PortraitWorker
from vanessa.knowledge.sweep import SweepAnalyzer, SweepWorker
from vanessa.knowledge.vault import KnowledgeVault
from vanessa.knowledge.vector_index import KnowledgeVectorIndexer
from vanessa.knowledge.writer import KnowledgeVaultWriter
from vanessa.pipeline.rag.embeddings.local_embeddings import preload_embedding_model

configure_logging("api")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.api_auto_create_schema:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.warning("API_AUTO_CREATE_SCHEMA enabled: used create_all")
    await create_vector_store().ensure_collection()
    # Bounded background executor for non-critical post-reply work (memory,
    # metrics, message indexing). Must be running before the app serves /chat.
    get_app_container().background.start()
    vault = KnowledgeVault()
    await vault.ensure_structure()
    # Bound person-context memory at startup: sort + time-bucket «Контекст
    # жизни» and move the overflow into the unused _archive (idempotent).
    try:
        await compact_all_person_cards(vault)
    except Exception:
        logger.exception("knowledge_compaction_failed at startup")
    vault_index = KnowledgeIndex(vault)
    knowledge_vector_indexer = KnowledgeVectorIndexer(
        vault,
        create_embedding_provider(),
        get_app_container().knowledge_vector_store,
    )

    sweep_task: asyncio.Task | None = None
    portrait_task: asyncio.Task | None = None
    # In worker mode the sweep/portrait loops run in the dedicated worker
    # container (isolated CPU/RAM); the API does not start them here.
    if settings.knowledge_sweep_enabled and not settings.worker_enabled:
        metrics_pipeline = MetricsPipeline(
            MetricsStore(vault, vault_index),
            MetricsPlanner(),
            DeterministicMetricsCalculator(
                history_days=settings.knowledge_metrics_history_days
            ),
            enabled=settings.knowledge_metrics_enabled,
        )
        sweep = SweepAnalyzer(
            vault,
            MemoryPlanner(),
            KnowledgeVaultWriter(
                vault,
                vault_index,
                vector_indexer=knowledge_vector_indexer,
            ),
            interval_messages=settings.knowledge_sweep_interval_messages,
            batch_size=settings.knowledge_sweep_batch_size,
            window_size=settings.knowledge_sweep_window_size,
            window_overlap=settings.knowledge_sweep_window_overlap,
            metrics=metrics_pipeline,
        )
        worker = SweepWorker(
            sweep,
            async_session_factory,
            poll_seconds=settings.knowledge_sweep_poll_seconds,
        )
        sweep_task = asyncio.create_task(worker.run_forever())

    # Hierarchical dossier summarization: periodically compress each People card
    # into a compact portrait so the compose prompt never dumps a 100+ line
    # dossier as background context.
    if settings.knowledge_portrait_enabled and not settings.worker_enabled:
        portrait_worker = PortraitWorker(
            PortraitBuilder(vault),
            poll_seconds=settings.knowledge_portrait_poll_seconds,
        )
        portrait_task = asyncio.create_task(portrait_worker.run_forever())

    await asyncio.to_thread(preload_embedding_model)
    await create_embedding_provider().embed("warmup")
    # Observability: in-process alerting (error rate / latency p95 / balance).
    alert_task: asyncio.Task | None = None
    alert_manager = create_alert_manager()
    if alert_manager is not None:
        alert_task = asyncio.create_task(alert_manager.run_forever())
        logger.info("AlertManager started (chat_id=%s)", settings.alerting_dev_chat_id)

    # Broker transport (Redis Streams): consume turns in-process and relay
    # outbox rows. Only started when the bot is configured to use the broker.
    broker_task: asyncio.Task | None = None
    outbox_task: asyncio.Task | None = None
    broker_metrics_task: asyncio.Task | None = None
    broker = None
    if settings.transport == "redis":
        from uuid import uuid4

        from services.agent_core.broker_worker import BrokerTurnWorker
        from vanessa.infrastructure.broker.metrics_collector import BrokerMetricsCollector
        from vanessa.infrastructure.broker.redis_streams import RedisStreamBroker
        from vanessa.infrastructure.broker.streams import BrokerStreams
        from vanessa.infrastructure.outbox.relay import OutboxRelay

        streams = BrokerStreams.from_settings(settings)
        broker = RedisStreamBroker(
            settings.broker_redis_url,
            stream_maxlen=settings.broker_stream_maxlen,
            dlq_enabled=settings.broker_dlq_enabled,
        )
        consumer_suffix = settings.broker_consumer_id or uuid4().hex[:6]
        turn_worker = BrokerTurnWorker(
            broker,
            stream=streams.turns,
            group=settings.broker_group_agent_core,
            consumer=f"{settings.broker_group_agent_core}-{consumer_suffix}",
            dedup=broker.dedup_guard(),
        )
        broker_task = asyncio.create_task(turn_worker.run_forever())
        logger.info(
            "broker_turn_worker_started stream=%s group=%s",
            streams.turns,
            settings.broker_group_agent_core,
        )
        if settings.outbox_enabled:
            outbox_relay = OutboxRelay(
                broker,
                async_session_factory,
                poll_seconds=settings.outbox_poll_seconds,
                batch_size=settings.outbox_batch_size,
                max_attempts=settings.outbox_max_attempts,
            )
            outbox_task = asyncio.create_task(outbox_relay.run_forever())
            logger.info("outbox_relay_started")
        broker_metrics_collector = BrokerMetricsCollector(
            broker,
            streams,
            groups=[
                (streams.turns, settings.broker_group_agent_core),
                (streams.tasks, settings.broker_group_worker),
            ],
            poll_seconds=15.0,
        )
        broker_metrics_task = asyncio.create_task(
            broker_metrics_collector.run_forever()
        )

    async def _index_vault() -> None:
        try:
            await knowledge_vector_indexer.index_all()
        except Exception:
            logger.exception("knowledge_vector_index_all_failed at startup")

    index_task = asyncio.create_task(_index_vault())

    yield

    index_task.cancel()
    try:
        await index_task
    except asyncio.CancelledError:
        pass

    if alert_task is not None:
        alert_task.cancel()
        try:
            await alert_task
        except asyncio.CancelledError:
            pass
    if sweep_task is not None:
        sweep_task.cancel()
        try:
            await sweep_task
        except asyncio.CancelledError:
            pass
    if portrait_task is not None:
        portrait_task.cancel()
        try:
            await portrait_task
        except asyncio.CancelledError:
            pass
    for task, name in (
        (broker_task, "broker_turn_worker"),
        (outbox_task, "outbox_relay"),
        (broker_metrics_task, "broker_metrics"),
    ):
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("%s stopped", name)
    if broker is not None:
        await broker.close()
    await get_app_container().background.shutdown()
    await engine.dispose()


app = FastAPI(
    title="Vanessa API",
    description="API для Telegram-бота Vanessa с RAG",
    version="0.1.0",
    lifespan=lifespan,
)

register_request_id_middleware(app)

app.include_router(health.router, tags=["health"])
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(notes.router, prefix="/api/v1", tags=["notes"])
app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
# Prometheus scrape endpoint (root /metrics; /api/v1/metrics stays the JSON snapshot).
app.include_router(observability.router)
