#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from alembic.config import Config

from alembic import command
from vanessa.core.logging_setup import configure_logging
from vanessa.infrastructure.db.repository import MessageRepository, UserRepository
from vanessa.infrastructure.db.session import async_session_factory
from vanessa.infrastructure.db.uow import SqlAlchemyUnitOfWork
from vanessa.infrastructure.ingest.importer import HistoryImporter
from vanessa.infrastructure.ingest.telegram_export import parse_telegram_export

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

configure_logging("import")
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import Telegram Desktop export (result.json) into Postgres.",
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
        help="Messages per DB batch",
    )
    return parser


def apply_migrations() -> None:
    logger.info("Applying database migrations...")
    alembic_cfg = Config(_PROJECT_ROOT / "alembic.ini")
    command.upgrade(alembic_cfg, "head")


def _load_messages(export_path: Path):
    if not export_path.is_file():
        logger.error("Export file not found: %s", export_path)
        return None
    metadata, messages = parse_telegram_export(export_path)
    if not messages:
        logger.error("No text messages found in export")
        return None
    return metadata, messages


async def run(args: argparse.Namespace) -> int:
    loaded = _load_messages(args.export)
    if loaded is None:
        return 1
    metadata, messages = loaded

    logger.info(
        "Preparing import: %s messages from %r",
        len(messages),
        metadata.get("name"),
    )

    async with async_session_factory() as session:
        uow = SqlAlchemyUnitOfWork(session)
        try:
            importer = HistoryImporter(
                messages=MessageRepository(session),
                users=UserRepository(session),
                unit_of_work=uow,
                batch_size=args.batch_size,
            )
            imported, skipped = await importer.import_messages(
                parsed_messages=messages,
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
