#!/usr/bin/env python
"""Preflight check for Telegram history import — validates the export, Postgres
and Qdrant state without writing anything. Safe to run any time.

Run from the host with Postgres/Qdrant up:

    POSTGRES_HOST=localhost QDRANT_HOST=localhost \\
      poetry run python scripts/preflight_import.py --export result.json --check-model
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.core.logging_setup import configure_logging
from app.config import settings
from app.db.session import async_session_factory
from app.ingest.telegram_export import parse_telegram_export

configure_logging("preflight")
logger = logging.getLogger(__name__)

# Chunk size for the dedup-overlap query (avoids hitting PG's 65535 param limit).
_CHUNK = 5000


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preflight check for Telegram history import (no writes).",
    )
    parser.add_argument(
        "--export",
        required=True,
        type=Path,
        help="Path to result.json from Telegram Desktop export",
    )
    parser.add_argument(
        "--check-model",
        action="store_true",
        help="Preload the embedding model (downloads it into the local HF cache if absent)",
    )
    return parser


async def check_model() -> None:
    from app.rag.embeddings.local_embeddings import preload_embedding_model

    logger.info("Preloading embedding model %r ...", settings.embedding_model_name)
    await asyncio.to_thread(preload_embedding_model)
    logger.info("Embedding model is ready.")


async def check_db(telegram_ids: set[int]) -> None:
    from sqlalchemy import func, select

    from app.db.models import Message

    async with async_session_factory() as session:
        total = (
            await session.execute(select(func.count(Message.id)))
        ).scalar_one()
        with_qdrant = (
            await session.execute(
                select(func.count(Message.id)).where(
                    Message.qdrant_point_id.is_not(None),
                )
            )
        ).scalar_one()
        max_tg = (
            await session.execute(select(func.max(Message.telegram_message_id)))
        ).scalar_one()

        existing = 0
        ids = list(telegram_ids)
        for start in range(0, len(ids), _CHUNK):
            chunk = ids[start : start + _CHUNK]
            result = await session.execute(
                select(Message.telegram_message_id).where(
                    Message.telegram_message_id.in_(chunk),
                )
            )
            existing += len(result.all())

    logger.info(
        "Postgres: total messages=%s, with qdrant_point_id=%s, max telegram id=%s",
        total,
        with_qdrant,
        max_tg,
    )
    logger.info(
        "Overlap: %s of %s export telegram ids already stored (would be skipped)",
        existing,
        len(ids),
    )


async def check_qdrant() -> None:
    from qdrant_client import AsyncQdrantClient

    client = AsyncQdrantClient(url=settings.qdrant_url)
    try:
        info = await client.get_collection(settings.qdrant_collection)
        logger.info(
            "Qdrant collection %r: vectors=%s, status=%s",
            settings.qdrant_collection,
            info.points_count,
            info.status,
        )
    except Exception as exc:  # pragma: no cover - best-effort diagnostics
        logger.warning("Could not read Qdrant collection: %s", exc)
    finally:
        await client.close()


async def run(args: argparse.Namespace) -> int:
    export_path: Path = args.export
    if not export_path.is_file():
        logger.error("Export file not found: %s", export_path)
        return 1

    logger.info("Parsing export: %s", export_path)
    metadata, messages = parse_telegram_export(export_path)
    if not messages:
        logger.error("No text messages found in export")
        return 1

    ids = {message.telegram_message_id for message in messages}
    senders = sorted(
        {message.sender_display_name for message in messages if message.sender_display_name}
    )
    dates = [message.created_at for message in messages]

    logger.info(
        "Export %r: raw messages=%s, parsed text=%s, distinct ids=%s, senders=%s",
        metadata.get("name"),
        len(metadata.get("messages", [])),
        len(messages),
        len(ids),
        len(senders),
    )
    if senders:
        shown = ", ".join(senders[:20])
        if len(senders) > 20:
            shown += ", ..."
        logger.info("Senders: %s", shown)
    if dates:
        logger.info(
            "Date range: %s .. %s",
            min(dates).isoformat(),
            max(dates).isoformat(),
        )

    await check_qdrant()
    await check_db(ids)

    if args.check_model:
        await check_model()

    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
