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

from app.config import settings
from app.core.logging_setup import configure_logging
from app.db.repository import MessageRepository, UserRepository
from app.db.session import async_session_factory
from app.db.uow import SqlAlchemyUnitOfWork
from app.ingest.telegram_export import extract_sender_names_from_export
from app.ingest.telegram_users import fetch_telegram_users
from app.ingest.user_backfill import UserBackfillService, load_nicknames

configure_logging("backfill")
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create or update users from messages. "
            "Profiles are fetched via Telegram getChat; "
            "optional lore nicknames from config/nicknames.yaml."
        ),
    )
    parser.add_argument(
        "--nicknames",
        type=Path,
        default=Path(settings.nicknames_config_path),
        help="Optional YAML: telegram_id -> lore nickname",
    )
    parser.add_argument(
        "--force-nicknames",
        action="store_true",
        help="Overwrite existing nicknames from --nicknames file",
    )
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Skip Telegram getChat profile lookup",
    )
    parser.add_argument(
        "--export-names",
        type=Path,
        help="result.json: extract sender display names (from/from_id only)",
    )
    return parser


def apply_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    logger.info("Applying database migrations...")
    alembic_cfg = Config(_PROJECT_ROOT / "alembic.ini")
    command.upgrade(alembic_cfg, "head")


async def run(args: argparse.Namespace) -> int:
    nicknames = load_nicknames(args.nicknames) if args.nicknames.is_file() else {}
    if nicknames:
        logger.info("Loaded %s lore nicknames from %s", len(nicknames), args.nicknames)

    export_names: dict[int, str] = {}
    if args.export_names is not None:
        if not args.export_names.is_file():
            logger.error("Export file not found: %s", args.export_names)
            return 1
        logger.info("Extracting sender names from %s ...", args.export_names)
        export_names = extract_sender_names_from_export(args.export_names)
        logger.info("Export has %s sender names", len(export_names))

    async with async_session_factory() as session:
        messages = MessageRepository(session)
        sender_ids = await messages.get_distinct_sender_telegram_ids()

        telegram_profiles = {}
        if not args.no_telegram:
            if not settings.telegram_bot_token:
                logger.error("TELEGRAM_BOT_TOKEN is not set")
                return 1
            logger.info("Fetching %s profiles from Telegram getChat...", len(sender_ids))
            telegram_profiles = await fetch_telegram_users(
                sender_ids,
                settings.telegram_bot_token,
            )
            logger.info(
                "Telegram returned %s/%s profiles",
                len(telegram_profiles),
                len(sender_ids),
            )

        uow = SqlAlchemyUnitOfWork(session)
        try:
            service = UserBackfillService(
                messages=messages,
                users=UserRepository(session),
                unit_of_work=uow,
            )
            result = await service.run(
                nicknames=nicknames,
                telegram_profiles=telegram_profiles,
                export_names=export_names,
                force_nicknames=args.force_nicknames,
            )
        except Exception:
            await uow.rollback()
            raise

    logger.info(
        "Done. senders=%s telegram=%s created=%s updated=%s unchanged=%s",
        result.sender_ids,
        result.telegram_fetched,
        result.created,
        result.updated,
        result.unchanged,
    )
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    apply_migrations()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
