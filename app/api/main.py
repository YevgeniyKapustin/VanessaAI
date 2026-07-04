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
from app.db.session import engine
from app.rag.local_embeddings import preload_embedding_model

configure_logging("api")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.api_auto_create_schema:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.warning("API_AUTO_CREATE_SCHEMA enabled: used create_all")
    await create_vector_store().ensure_collection()
    await asyncio.to_thread(preload_embedding_model)
    await create_embedding_provider().embed("warmup")
    yield
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
