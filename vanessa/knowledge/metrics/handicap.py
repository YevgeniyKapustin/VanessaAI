"""Owner handicap: floors for the card of the account that tests Vanessa.

The owner pokes and provokes Vanessa on purpose to tune her behaviour, so a
testing turn is not a verdict on the relationship. The handicap clamps the
semantic block of the owner's card after extraction: floors for the friendly
fields, ceilings for the hostile ones. Deterministic counters (messages,
presence, reaction time) are facts and stay untouched.
"""

from __future__ import annotations

from dataclasses import replace

from vanessa.config.content_sections import MetricsHandicapContent
from vanessa.config.owners import owner_telegram_ids
from vanessa.knowledge.metrics.schema import Distance, PersonMetrics

_DISTANCE_ORDER = (
    Distance.FORMAL,
    Distance.BUSINESS,
    Distance.NEUTRAL,
    Distance.FRIENDLY,
    Distance.FAMILIAR,
)


def _floor(value: float | None, floor: float, lo: float, hi: float) -> float:
    """Raise a value to ``floor``, filling a missing value with it."""
    base = floor if value is None else max(value, floor)
    return max(lo, min(hi, base))


def _ceiling(value: float | None, ceiling: float, lo: float, hi: float) -> float | None:
    """Lower a value to ``ceiling``; a missing value cannot be lowered."""
    if value is None:
        return None
    return max(lo, min(hi, value, ceiling))


def _parse_distance(raw: str) -> Distance | None:
    text = (raw or "").strip().lower()
    for candidate in Distance:
        if candidate.value == text:
            return candidate
    return None


def _distance_floor(current: Distance | None, floor: Distance | None) -> Distance | None:
    if floor is None:
        return current
    if current is None:
        return floor
    rank = max(_DISTANCE_ORDER.index(current), _DISTANCE_ORDER.index(floor))
    return _DISTANCE_ORDER[rank]


def apply_handicap(
    metrics: PersonMetrics, handicap: MetricsHandicapContent
) -> PersonMetrics:
    """Clamp one snapshot to the handicap floors and ceilings."""
    return replace(
        metrics,
        trust_score=int(_floor(metrics.trust_score, handicap.trust_score, 0, 100)),
        valence=_floor(metrics.valence, handicap.valence, -1.0, 1.0),
        sympathy=_floor(metrics.sympathy, handicap.sympathy, -1.0, 1.0),
        constructiveness=_floor(
            metrics.constructiveness, handicap.constructiveness, 0.0, 1.0
        ),
        support_index=_floor(metrics.support_index, handicap.support_index, 0.0, 1.0),
        toxicity=_ceiling(metrics.toxicity, handicap.toxicity, 0.0, 1.0),
        sarcasm_index=_ceiling(metrics.sarcasm_index, handicap.sarcasm_index, 0.0, 1.0),
        distance=_distance_floor(metrics.distance, _parse_distance(handicap.distance)),
    )


def apply_owner_handicap(
    combined: dict[str, tuple[int | None, str | None, PersonMetrics]],
    handicap: MetricsHandicapContent,
) -> None:
    """Clamp the owner's rows of a combined metrics batch in place."""
    owners = owner_telegram_ids()
    if not handicap.enabled or not owners:
        return
    for person_id, (telegram_id, name, metrics) in list(combined.items()):
        if telegram_id in owners:
            combined[person_id] = (telegram_id, name, apply_handicap(metrics, handicap))
