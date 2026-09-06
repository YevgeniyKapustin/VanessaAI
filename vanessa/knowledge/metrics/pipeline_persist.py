"""Persist merged mood/relationship snapshots onto person cards."""

from __future__ import annotations

from vanessa.knowledge.format import today
from vanessa.knowledge.metrics.schema import MetricsSnapshot, PersonMetrics
from vanessa.knowledge.metrics.store import MetricsStore


def _metrics_to_store(
    current: PersonMetrics | None, metrics: PersonMetrics
) -> PersonMetrics | None:
    if current is None:
        return metrics
    merged = current.merged(metrics)
    if merged.to_dict(include_updated=False) == current.to_dict(include_updated=False):
        return None
    return merged


async def persist_combined(
    store: MetricsStore,
    combined: dict[str, tuple[int | None, str | None, PersonMetrics]],
) -> tuple[int, int]:
    stored = 0
    skipped = 0
    for person_id, (telegram_id, name, metrics) in combined.items():
        current = await store.load_snapshot(person_id)
        to_store = _metrics_to_store(current, metrics)
        if to_store is None:
            skipped += 1
            continue
        snapshot = MetricsSnapshot(
            person=person_id,
            name=name,
            metrics=to_store.with_updated(today()),
            telegram_id=telegram_id,
        )
        if await store.store_snapshot(snapshot):
            stored += 1
    return stored, skipped
