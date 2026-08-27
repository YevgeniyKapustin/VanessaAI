from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI

from app.api.container import get_app_container
from app.api.deps import create_embedding_provider, create_vector_store
from app.api.middleware import register_request_id_middleware
from app.api.routes import chat, health, metrics, observability
from app.config import settings
from app.core.logging_setup import configure_logging
from app.observability.alerting import create_alert_manager
from app.db.base import Base
from app.db.session import async_session_factory, engine
from app.knowledge.compaction import compact_all_person_cards
from app.knowledge.index import KnowledgeIndex
from app.knowledge.memory_planner import MemoryPlanner
from app.knowledge.metrics.deterministic import DeterministicMetricsCalculator
from app.knowledge.metrics.pipeline import MetricsPipeline
from app.knowledge.metrics.planner import MetricsPlanner
from app.knowledge.metrics.store import MetricsStore
from app.knowledge.portraits import PortraitBuilder, PortraitWorker
from app.knowledge.sweep import SweepAnalyzer, SweepWorker
from app.knowledge.vault import KnowledgeVault
from app.knowledge.vector_index import KnowledgeVectorIndexer
from app.knowledge.writer import KnowledgeVaultWriter
from app.rag.embeddings.local_embeddings import preload_embedding_model

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
    if settings.knowledge_sweep_enabled:
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
    if settings.knowledge_portrait_enabled:
        portrait_worker = PortraitWorker(
            PortraitBuilder(vault),
            poll_seconds=settings.knowledge_portrait_poll_seconds,
        )
        portrait_task = asyncio.create_task(portrait_worker.run_forever())

    await asyncio.to_thread(preload_embedding_model)
    await create_embedding_provider().embed("warmup")
    # Seed/refresh the semantic vault vector index once at startup (fail-open —
    # a full reindex can be rerun via scripts/reindex_knowledge_vectors.py).
    try:
        await knowledge_vector_indexer.index_all()
    except Exception:
        logger.exception("knowledge_vector_index_all_failed at startup")
    # Observability: in-process alerting (error rate / latency p95 / balance).
    alert_task: asyncio.Task | None = None
    alert_manager = create_alert_manager()
    if alert_manager is not None:
        alert_task = asyncio.create_task(alert_manager.run_forever())
        logger.info("AlertManager started (chat_id=%s)", settings.alerting_dev_chat_id)

    yield

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
app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
# Prometheus scrape endpoint (root /metrics; /api/v1/metrics stays the JSON snapshot).
app.include_router(observability.router)
