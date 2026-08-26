from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI

from app.api.deps import create_embedding_provider, create_vector_store
from app.api.middleware import register_request_id_middleware
from app.api.routes import chat, health, metrics
from app.config import settings
from app.core.logging_setup import configure_logging
from app.db.base import Base
from app.db.session import async_session_factory, engine
from app.knowledge.index import KnowledgeIndex
from app.knowledge.memory_planner import MemoryPlanner
from app.knowledge.metrics.deterministic import DeterministicMetricsCalculator
from app.knowledge.metrics.pipeline import MetricsPipeline
from app.knowledge.metrics.planner import MetricsPlanner
from app.knowledge.metrics.store import MetricsStore
from app.knowledge.sweep import SweepAnalyzer, SweepWorker
from app.knowledge.vault import KnowledgeVault
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
    vault = KnowledgeVault()
    await vault.ensure_structure()

    sweep_task: asyncio.Task | None = None
    if settings.knowledge_sweep_enabled:
        vault_index = KnowledgeIndex(vault)
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
            KnowledgeVaultWriter(vault, vault_index),
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

    await asyncio.to_thread(preload_embedding_model)
    await create_embedding_provider().embed("warmup")
    yield

    if sweep_task is not None:
        sweep_task.cancel()
        try:
            await sweep_task
        except asyncio.CancelledError:
            pass
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
