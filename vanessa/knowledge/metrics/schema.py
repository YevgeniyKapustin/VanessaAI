"""Metrics value objects: PersonMetrics — a typed mood & relationship snapshot.

Every value lives in a fixed range (part of the contract) and is clamped on
input, so the vault never stores out-of-range numbers and the decision/tone
feedback can rely on the ranges.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from vanessa.knowledge.format import today


class Distance(StrEnum):
    """Communication distance the participant keeps with Vanessa."""

    FORMAL = "formal"
    BUSINESS = "business"
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    FAMILIAR = "familiar"


def _clamp_float(value: object, lo: float, hi: float) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(lo, min(hi, number))


def _clamp_int(value: object, lo: int, hi: int | None = None) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    if hi is not None:
        number = max(lo, min(hi, number))
    elif number < lo:
        number = lo
    return number


def _parse_distance(value: object) -> Distance | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    for candidate in Distance:
        if candidate.value == text:
            return candidate
    return None


@dataclass(frozen=True, slots=True)
class PersonMetrics:
    """A per-person metrics snapshot. All fields are optional and clamped."""

    # --- Group 1: emotional tone & valence (LLM) ---
    valence: float | None = None  # [-1, 1]
    volatility: float | None = None  # [0, 1]
    sarcasm_index: float | None = None  # [0, 1]

    # --- Group 2: engagement & dynamics (LLM + counters) ---
    constructiveness: float | None = None  # [0, 1]
    toxicity: float | None = None  # [0, 1]
    support_index: float | None = None  # [0, 1]

    # --- Group 3: relational to Vanessa (LLM, subjective) ---
    trust_score: int | None = None  # [0, 100]
    distance: Distance | None = None
    sympathy: float | None = None  # [-1, 1]

    # --- Group 4: behavioral meta (deterministic) ---
    presence_stability: float | None = None  # [0, 1]
    reactivity_median_s: int | None = None  # >= 0
    peak_hour: int | None = None  # [0, 23]
    active_days: int | None = None  # >= 0
    message_count: int | None = None  # >= 0
    reply_rate_to_bot: float | None = None  # [0, 1]

    updated: str | None = None  # snapshot date YYYY-MM-DD

    def to_dict(self, *, include_updated: bool = True) -> dict:
        """Serialize to a plain dict (only non-None values; enum -> value)."""
        result: dict = {}
        for field_name in _SERIALIZED_FIELDS:
            value = getattr(self, field_name)
            if value is None:
                continue
            result[field_name] = value.value if isinstance(value, Distance) else value
        if include_updated and self.updated:
            result["updated"] = self.updated
        return result

    @classmethod
    def from_dict(cls, data: dict) -> PersonMetrics:
        data = data if isinstance(data, dict) else {}
        return cls(
            valence=_clamp_float(data.get("valence"), -1.0, 1.0),
            volatility=_clamp_float(data.get("volatility"), 0.0, 1.0),
            sarcasm_index=_clamp_float(data.get("sarcasm_index"), 0.0, 1.0),
            constructiveness=_clamp_float(data.get("constructiveness"), 0.0, 1.0),
            toxicity=_clamp_float(data.get("toxicity"), 0.0, 1.0),
            support_index=_clamp_float(data.get("support_index"), 0.0, 1.0),
            trust_score=_clamp_int(data.get("trust_score"), 0, 100),
            distance=_parse_distance(data.get("distance")),
            sympathy=_clamp_float(data.get("sympathy"), -1.0, 1.0),
            presence_stability=_clamp_float(data.get("presence_stability"), 0.0, 1.0),
            reactivity_median_s=_clamp_int(data.get("reactivity_median_s"), 0),
            peak_hour=_clamp_int(data.get("peak_hour"), 0, 23),
            active_days=_clamp_int(data.get("active_days"), 0),
            message_count=_clamp_int(data.get("message_count"), 0),
            reply_rate_to_bot=_clamp_float(data.get("reply_rate_to_bot"), 0.0, 1.0),
            updated=str(data["updated"]) if data.get("updated") else None,
        )

    @classmethod
    def zero(cls) -> PersonMetrics:
        """A neutral/zero baseline for a brand-new participant.

        Every numeric field defaults to zero (and ``distance`` to its neutral
        value) so a fresh card is never an empty shell: every chat member gets a
        visible baseline after their very first message, and Vanessa moves values
        off zero as she gets to know the person.
        """
        return cls(
            valence=0.0,
            volatility=0.0,
            sarcasm_index=0.0,
            constructiveness=0.0,
            toxicity=0.0,
            support_index=0.0,
            trust_score=0,
            distance=Distance.NEUTRAL,
            sympathy=0.0,
            presence_stability=0.0,
            reactivity_median_s=0,
            peak_hour=0,
            active_days=0,
            message_count=0,
            reply_rate_to_bot=0.0,
        )

    def merged(self, other: PersonMetrics) -> PersonMetrics:
        """Return a copy where ``other``'s non-None fields win over ``self``'s."""
        values: dict = {}
        for field_name in _ALL_FIELDS:
            base = getattr(self, field_name)
            override = getattr(other, field_name)
            values[field_name] = override if override is not None else base
        return replace(self, **values)

    def with_updated(self, value: str) -> PersonMetrics:
        return replace(self, updated=value)


_SERIALIZED_FIELDS = (
    "valence",
    "volatility",
    "sarcasm_index",
    "constructiveness",
    "toxicity",
    "support_index",
    "trust_score",
    "distance",
    "sympathy",
    "presence_stability",
    "reactivity_median_s",
    "peak_hour",
    "active_days",
    "message_count",
    "reply_rate_to_bot",
)

_ALL_FIELDS = (*_SERIALIZED_FIELDS, "updated")


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    """Identity + metrics values for one person in one plan."""

    person: str
    metrics: PersonMetrics
    telegram_id: int | None = None
    name: str | None = None  # display name used as a card alias for new people

    @property
    def date(self) -> str:
        return self.metrics.updated or today()
