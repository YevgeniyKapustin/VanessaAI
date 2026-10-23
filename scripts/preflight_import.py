#!/usr/bin/env python
"""Preflight check for Telegram history import — validates the export and
Postgres state without writing anything. Safe to run any time.

Run from the host with Postgres up:

    POSTGRES_HOST=localhost \\
      poetry run python scripts/preflight_import.py --export result.json
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import func, select

from scripts.preflight_import_report import (
    load_export,
    log_export_summary,
    sender_names,
)
from vanessa.core.logging_setup import configure_logging
from vanessa.infrastructure.db.models import Message
from vanessa.infrastructure.db.session import async_session_factory

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

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
    return parser


async def check_db(telegram_ids: set[int]) -> None:
    async with async_session_factory() as session:
        total = (
            await session.execute(select(func.count(Message.id)))
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
        "Postgres: total messages=%s, max telegram id=%s",
        total,
        max_tg,
    )
    logger.info(
        "Overlap: %s of %s export telegram ids already stored (would be skipped)",
        existing,
        len(ids),
    )


async def run(args: argparse.Namespace) -> int:
    loaded = load_export(args.export, logger)
    if loaded is None:
        return 1
    metadata, messages = loaded
    ids = {message.telegram_message_id for message in messages}
    senders = sender_names(messages)
    dates = [message.created_at for message in messages]
    log_export_summary(metadata, messages, ids, senders, dates, logger)
    await check_db(ids)
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
