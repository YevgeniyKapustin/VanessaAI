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
from vanessa.knowledge.format import today
from vanessa.knowledge.memory_stage import format_memory_transcript
from vanessa.knowledge.metrics.deterministic import DeterministicMetricsCalculator
from vanessa.knowledge.metrics.planner import MetricsPlanner
from vanessa.knowledge.metrics.schema import MetricsSnapshot, PersonMetrics
from vanessa.knowledge.metrics.store import MetricsStore

logger = logging.getLogger(__name__)

_TRANSCRIPT_LIMIT = 120


class MetricsPipeline:
    # Shared across instances: per-turn runs are built per request in the DI
    # container, so the cooldown must live at class level to actually throttle.
    _last_run: float = 0.0

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
        if not semantic and self._cooldown > 0:
            now = time.monotonic()
            if now - type(self)._last_run < self._cooldown:
                return 0

        if batch is None:
            batch = await repo.get_messages_since(
                days=self._calculator.history_days
            )
        det = self._calculator.compute_per_sender(batch)
        if only_senders is not None:
            # Per-turn pass: drop every other sender before any card is resolved
            # or written, so we only ever touch the active participant.
            det = {
                telegram_id: metrics
                for telegram_id, metrics in det.items()
                if telegram_id in only_senders
            }

        # First non-empty display name per sender, used as a card alias when a
        # brand-new participant gets their zero-baseline card.
        names_by_telegram: dict[int, str] = {}
        for message in batch:
            if message.sender_telegram_id is not None and message.sender_name:
                names_by_telegram.setdefault(
                    message.sender_telegram_id, message.sender_name
                )

        semantic_snapshots: tuple[MetricsSnapshot, ...] = ()
        if semantic and self._planner is not None:
            try:
                semantic_snapshots = await self._planner.decide(
                    self._transcript(batch)
                )
            except Exception:
                logger.exception("metrics_semantic_plan_failed")
                semantic_snapshots = ()

        combined: dict[str, tuple[int | None, str | None, PersonMetrics]] = {}
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

        stored = 0
        skipped = 0
        for person_id, (telegram_id, name, metrics) in combined.items():
            current = await self._store.load_snapshot(person_id)
            if current is not None:
                # Change detection: a card is only rewritten when at least one
                # metric value actually moved (``updated`` is excluded from the
                # comparison), so the pipeline stops churning unchanged cards.
                merged = current.merged(metrics)
                if merged.to_dict(include_updated=False) == current.to_dict(
                    include_updated=False
                ):
                    skipped += 1
                    continue
                metrics = merged
            snapshot = MetricsSnapshot(
                person=person_id,
                name=name,
                metrics=metrics.with_updated(today()),
                telegram_id=telegram_id,
            )
            if await self._store.store_snapshot(snapshot):
                stored += 1

        if not semantic:
            type(self)._last_run = time.monotonic()
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
