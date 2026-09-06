"""Export-summary logging for ``scripts/preflight_import.py``."""

from __future__ import annotations

import logging
from pathlib import Path

from vanessa.infrastructure.ingest.telegram_export import parse_telegram_export

_SENDER_PREVIEW_LIMIT = 20


def load_export(export_path: Path, logger: logging.Logger):
    if not export_path.is_file():
        logger.error("Export file not found: %s", export_path)
        return None
    logger.info("Parsing export: %s", export_path)
    metadata, messages = parse_telegram_export(export_path)
    if not messages:
        logger.error("No text messages found in export")
        return None
    return metadata, messages


def sender_names(messages) -> list[str]:
    return sorted(
        {
            message.sender_display_name
            for message in messages
            if message.sender_display_name
        }
    )


def _log_senders(senders: list[str], logger: logging.Logger) -> None:
    if not senders:
        return
    shown = ", ".join(senders[:_SENDER_PREVIEW_LIMIT])
    if len(senders) > _SENDER_PREVIEW_LIMIT:
        shown += ", ..."
    logger.info("Senders: %s", shown)


def _log_dates(dates, logger: logging.Logger) -> None:
    if not dates:
        return
    logger.info(
        "Date range: %s .. %s",
        min(dates).isoformat(),
        max(dates).isoformat(),
    )


def log_export_summary(
    metadata,
    messages,
    ids,
    senders,
    dates,
    logger: logging.Logger,
) -> None:
    logger.info(
        "Export %r: raw messages=%s, parsed text=%s, distinct ids=%s, senders=%s",
        metadata.get("name"),
        len(metadata.get("messages", [])),
        len(messages),
        len(ids),
        len(senders),
    )
    _log_senders(senders, logger)
    _log_dates(dates, logger)
