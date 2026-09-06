"""Range clamping for PersonMetrics numeric fields."""

from __future__ import annotations


def _bounded_int(number: int, lo: int, hi: int | None) -> int:
    if hi is None:
        return max(lo, number)
    return max(lo, min(hi, number))


def clamp_int(value: object, lo: int, hi: int | None = None) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return _bounded_int(number, lo, hi)
