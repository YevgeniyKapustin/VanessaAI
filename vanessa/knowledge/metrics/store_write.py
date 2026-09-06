"""Snapshot write helpers for MetricsStore."""

from __future__ import annotations

import logging
from dataclasses import replace

from vanessa.knowledge.format import PEOPLE
from vanessa.knowledge.metrics.schema import MetricsSnapshot, PersonMetrics
from vanessa.knowledge.schema import VaultNote

logger = logging.getLogger("vanessa.knowledge.metrics.store")


def zero_if_new(snapshot: MetricsSnapshot, note: VaultNote | None) -> MetricsSnapshot:
    if note is not None:
        return snapshot
    # Brand-new participant: start from a zero baseline so every chat
    # member has metrics from their very first message. Vanessa may then
    # move values off zero through the semantic metrics planner.
    return replace(
        snapshot,
        metrics=PersonMetrics.zero().merged(snapshot.metrics),
    )


def snapshot_paths(card: str | None, *, created_card: bool) -> list[str]:
    if not card:
        return []
    paths = [card]
    if created_card:
        paths.append(f"{PEOPLE}/_index.yaml")
    return paths


def log_snapshot_stored(person_id: str, paths: list[str]) -> None:
    if not paths:
        return
    logger.info(
        "metrics_snapshot_stored person=%s paths=%s",
        person_id,
        len(paths),
    )
