#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from vanessa.config import settings
from vanessa.core.logging_setup import configure_logging
from vanessa.infrastructure.db.repository import MessageRepository, UserRepository
from vanessa.infrastructure.db.session import async_session_factory
from vanessa.infrastructure.db.uow import SqlAlchemyUnitOfWork
from vanessa.infrastructure.ingest.importer import HistoryImporter
from vanessa.infrastructure.ingest.telegram_export import parse_telegram_export
from vanessa.pipeline.rag.embeddings.embeddings import LocalEmbeddingProvider
from vanessa.pipeline.rag.embeddings.local_embeddings import preload_embedding_model
from vanessa.pipeline.rag.qdrant_client import QdrantVectorStore

configure_logging("import")
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import Telegram Desktop export (result.json) into Postgres and Qdrant.",
    )
    parser.add_argument(
        "--export",
        required=True,
        type=Path,
        help="Path to result.json from Telegram Desktop export",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Messages per DB/embed batch",
    )
    parser.add_argument(
        "--no-embed",
        action="store_true",
        help="Store messages in Postgres only, skip Qdrant indexing",
    )
    return parser


def apply_migrations() -> None:
    from alembic.config import Config

    from alembic import command

    logger.info("Applying database migrations...")
    alembic_cfg = Config(_PROJECT_ROOT / "alembic.ini")
    command.upgrade(alembic_cfg, "head")


async def run(args: argparse.Namespace) -> int:
    export_path: Path = args.export
    if not export_path.is_file():
        logger.error("Export file not found: %s", export_path)
        return 1

    metadata, messages = parse_telegram_export(export_path)
    if not messages:
        logger.error("No text messages found in export")
        return 1

    logger.info(
        "Preparing import: %s messages from %r",
        len(messages),
        metadata.get("name"),
    )

    embeddings = LocalEmbeddingProvider()
    vector_store = QdrantVectorStore()
    if not args.no_embed:
        logger.info("Loading embedding model: %s", settings.embedding_model_name)
        preload_embedding_model()

    async with async_session_factory() as session:
        uow = SqlAlchemyUnitOfWork(session)
        try:
            importer = HistoryImporter(
                messages=MessageRepository(session),
                users=UserRepository(session),
                embeddings=embeddings,
                vector_store=vector_store,
                unit_of_work=uow,
                batch_size=args.batch_size,
            )
            imported, skipped = await importer.import_messages(
                parsed_messages=messages,
                embed=not args.no_embed,
            )
        except Exception:
            await uow.rollback()
            raise

    logger.info("Done. Imported=%s, skipped=%s", imported, skipped)
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    apply_migrations()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
