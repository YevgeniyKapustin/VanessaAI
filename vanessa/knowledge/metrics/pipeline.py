"""MetricsPipeline: compute + persist mood & relationship snapshots.

Deterministic fields (presence, activity, reactivity, counters) come from the
message DB; semantic fields (valence, toxicity, trust, ...) come from the
MetricsPlanner LLM. Both are merged with the existing card snapshot so no
previously known value is lost, then stored once per person.

Two modes:

- ``semantic=False`` (per-turn, throttled by cooldown): deterministic only, no
  LLM call — cheap freshness for the sender the bot just interacted with.
- ``semantic=True`` (background sweep): full pass — deterministic over the
  14-day window + semantic LLM scoring of the transcript.
"""

from __future__ import annotations

import logging
import time

from vanessa.core.messages import StoredMessage, stored_to_context
from vanessa.knowledge.memory.memory_stage import format_memory_transcript
from vanessa.knowledge.metrics.deterministic import DeterministicMetricsCalculator
from vanessa.knowledge.metrics.pipeline_persist import persist_combined
from vanessa.knowledge.metrics.planner import MetricsPlanner
from vanessa.knowledge.metrics.schema import MetricsSnapshot, PersonMetrics
from vanessa.knowledge.metrics.store import MetricsStore

logger = logging.getLogger(__name__)

_TRANSCRIPT_LIMIT = 120


def _cooldown_blocks(last_run: float | None, cooldown: int, *, semantic: bool) -> bool:
    if semantic or cooldown <= 0 or last_run is None:
        return False
    return time.monotonic() - last_run < cooldown


def _filter_sender_metrics(
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


class MetricsPipeline:
    # Shared across instances: per-turn runs are built per request in the DI
    # container, so the cooldown must live at class level to actually throttle.
    _last_run: float | None = None

    def __init__(
        self,
        store: MetricsStore,
        planner: MetricsPlanner | None,
        calculator: DeterministicMetricsCalculator | None = None,
        *,
        enabled: bool = True,
        cooldown_seconds: int = 900,
    ) -> None:
        self._store = store
        self._planner = planner
        self._calculator = calculator or DeterministicMetricsCalculator()
        self._enabled = enabled
        self._cooldown = max(0, cooldown_seconds)

    def _touch_last_run(self, *, semantic: bool) -> None:
        if semantic:
            return
        type(self)._last_run = time.monotonic()

    async def _semantic_snapshots(
        self, batch: list[StoredMessage], *, semantic: bool
    ) -> tuple[MetricsSnapshot, ...]:
        if not semantic or self._planner is None:
            return ()
        try:
            return await self._planner.decide(self._transcript(batch))
        except Exception:
            logger.exception("metrics_semantic_plan_failed")
            return ()

    async def _combine(
        self,
        batch: list[StoredMessage],
        det: dict[int, PersonMetrics],
        semantic_snapshots: tuple[MetricsSnapshot, ...],
    ) -> dict[str, tuple[int | None, str | None, PersonMetrics]]:
        names_by_telegram: dict[int, str] = {}
        for message in batch:
            if message.sender_telegram_id is not None and message.sender_name:
                names_by_telegram.setdefault(
                    message.sender_telegram_id, message.sender_name
                )
        combined: dict[str, tuple[int | None, str | None, PersonMetrics]] = {}
        await self._merge_semantic(combined, semantic_snapshots)
        await self._merge_deterministic(combined, det, names_by_telegram)
        return combined

    async def _merge_semantic(
        self,
        combined: dict[str, tuple[int | None, str | None, PersonMetrics]],
        semantic_snapshots: tuple[MetricsSnapshot, ...],
    ) -> None:
        for snap in semantic_snapshots:
            person_id = await self._store.resolve_person_id(
                snap.person, snap.telegram_id
            )
            if not person_id:
                continue
            existing = combined.get(person_id)
            metrics = snap.metrics
            if existing is not None:
                metrics = existing[2].merged(metrics)
            combined[person_id] = (snap.telegram_id, snap.name or snap.person, metrics)

    async def _merge_deterministic(
        self,
        combined: dict[str, tuple[int | None, str | None, PersonMetrics]],
        det: dict[int, PersonMetrics],
        names_by_telegram: dict[int, str],
    ) -> None:
        for telegram_id, det_metrics in det.items():
            name = names_by_telegram.get(telegram_id)
            person_id = await self._store.resolve_by_telegram_id(
                telegram_id, name=name
            )
            if not person_id:
                continue
            existing = combined.get(person_id)
            if existing is not None:
                merged = existing[2].merged(det_metrics)
                combined[person_id] = (
                    existing[0] or telegram_id,
                    existing[1] or name,
                    merged,
                )
            else:
                combined[person_id] = (telegram_id, name, det_metrics)

    async def _persist_combined(
        self,
        combined: dict[str, tuple[int | None, str | None, PersonMetrics]],
    ) -> tuple[int, int]:
        return await persist_combined(self._store, combined)

    async def run(
        self,
        repo,
        *,
        semantic: bool = False,
        batch: list[StoredMessage] | None = None,
        only_senders: set[int] | None = None,
    ) -> int:
        """Compute and persist metrics. Returns the number of snapshots stored.

        ``only_senders`` restricts the per-turn deterministic pass to a single
        active sender (the one the bot just interacted with) instead of
        rewriting every participant card on the 14-day window. It is ignored by
        the ``semantic=True`` sweep, which keeps processing the full batch.
        """
        if not self._enabled:
            return 0
        if _cooldown_blocks(type(self)._last_run, self._cooldown, semantic=semantic):
            return 0

        if batch is None:
            batch = await repo.get_messages_since(
                days=self._calculator.history_days
            )
        det = _filter_sender_metrics(
            self._calculator.compute_per_sender(batch), only_senders
        )

        semantic_snapshots = await self._semantic_snapshots(batch, semantic=semantic)
        combined = await self._combine(batch, det, semantic_snapshots)
        stored, skipped = await self._persist_combined(combined)

        self._touch_last_run(semantic=semantic)
        logger.info(
            "metrics_pipeline_done semantic=%s stored=%s skipped=%s",
            semantic,
            stored,
            skipped,
        )
        return stored

    @staticmethod
    def _transcript(messages: list[StoredMessage]) -> str:
        context = [stored_to_context(message) for message in messages]
        return format_memory_transcript(context[-_TRANSCRIPT_LIMIT:])
