"""Batch filters for the metrics pipeline."""

from __future__ import annotations

from vanessa.core.bot_senders import is_bot_sender_label
from vanessa.core.messages import StoredMessage
from vanessa.knowledge.metrics.schema import PersonMetrics


def drop_bot_messages(batch: list[StoredMessage]) -> list[StoredMessage]:
    """Drop messages of other AI bots: a bot never gets a person card."""
    return [
        message
        for message in batch
        if message.role != "user" or not is_bot_sender_label(message.sender_name)
    ]


def filter_sender_metrics(
    det: dict[int, PersonMetrics],
    only_senders: set[int] | None,
) -> dict[int, PersonMetrics]:
    if only_senders is None:
        return det
    # Per-turn pass: drop every other sender before any card is resolved
    # or written, so we only ever touch the active participant.
    return {
        telegram_id: metrics
        for telegram_id, metrics in det.items()
        if telegram_id in only_senders
    }
