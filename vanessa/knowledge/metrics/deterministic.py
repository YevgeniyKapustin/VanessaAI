"""DeterministicMetricsCalculator: behavioral meta-metrics from stored messages.

Presence stability, active days, peak activity hour, reactivity and counters
are computed from the message DB — no LLM involved. The calculator works on an
ascending list of ``StoredMessage`` (user + assistant) and returns per-sender
``PersonMetrics`` with only the deterministic fields populated.
"""

from __future__ import annotations

import logging
import statistics
from collections import Counter
from datetime import UTC, datetime

from vanessa.core.messages import RAG_SOURCE_ROLE, StoredMessage
from vanessa.knowledge.metrics.schema import PersonMetrics

logger = logging.getLogger(__name__)


def _local_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone()


class DeterministicMetricsCalculator:
    def __init__(self, history_days: int = 14) -> None:
        self._history_days = max(1, history_days)

    @property
    def history_days(self) -> int:
        """Rolling window (in days) used for presence/activity metrics."""
        return self._history_days

    def compute_per_sender(
        self,
        messages: list[StoredMessage],
    ) -> dict[int, PersonMetrics]:
        """Return deterministic metrics keyed by ``sender_telegram_id``."""
        by_sender: dict[int, dict] = {}
        previous: StoredMessage | None = None
        for message in messages:
            sender = message.sender_telegram_id
            if sender is None:
                previous = message
                continue
            if sender not in by_sender:
                by_sender[sender] = {
                    "count": 0,
                    "days": set(),
                    "hours": Counter(),
                    "replies_to_bot": 0,
                    "gaps": [],
                }
            stats = by_sender[sender]
            stats["count"] += 1
            local = _local_datetime(message.created_at)
            if local is not None:
                stats["days"].add(local.date())
                stats["hours"][local.hour] += 1
            if previous is not None:
                prev_local = _local_datetime(previous.created_at)
                if (
                    previous.sender_telegram_id != sender
                    and local is not None
                    and prev_local is not None
                ):
                    gap = (local - prev_local).total_seconds()
                    if gap >= 0:
                        stats["gaps"].append(gap)
                if previous.role != RAG_SOURCE_ROLE:
                    stats["replies_to_bot"] += 1
            previous = message

        result: dict[int, PersonMetrics] = {}
        for sender, stats in by_sender.items():
            days = stats["days"]
            span_days = 1
            if days:
                span_days = max(1, (max(days) - min(days)).days + 1)
            window = max(1, min(self._history_days, span_days))
            peak_hour = stats["hours"].most_common(1)[0][0] if stats["hours"] else None
            gaps = stats["gaps"]
            median_gap = round(statistics.median(gaps)) if gaps else None
            count = stats["count"]
            reply_rate = stats["replies_to_bot"] / count if count else None
            result[sender] = PersonMetrics(
                presence_stability=round(len(days) / window, 3),
                reactivity_median_s=median_gap,
                peak_hour=peak_hour,
                active_days=len(days),
                message_count=count,
                reply_rate_to_bot=(
                    round(reply_rate, 3) if reply_rate is not None else None
                ),
            )
        return result
