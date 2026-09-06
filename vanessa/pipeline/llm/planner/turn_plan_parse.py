from __future__ import annotations

import json

from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.llm.format.llm_json import normalize_llm_json
from vanessa.pipeline.llm.planner.turn_plan_build import (
    _clarification_plan,
    _search_plan,
    _skip_plan,
)


def _parse_loop_level(value: object) -> int:
    """Clamp the planner's loop_level to 0..3 (a bare ``true`` counts as 1)."""
    if isinstance(value, bool):
        return 1 if value else 0
    try:
        level = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(3, level))


def _load_planner_payload(raw: str) -> dict:
    normalized = normalize_llm_json(raw)
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        payload = {"search_query": normalized, "skip": False}
    return payload


def parse_llm_response(original: str, raw: str) -> TurnPlan:
    payload = _load_planner_payload(raw)
    reason = str(payload.get("reason", "")).strip()
    repeated_topic = payload.get("repeated_topic") is True
    loop_level = _parse_loop_level(payload.get("loop_level"))

    if payload.get("skip") is True:
        return _skip_plan(
            original,
            payload,
            reason,
            repeated_topic=repeated_topic,
            loop_level=loop_level,
        )

    if payload.get("needs_clarification") is True:
        return _clarification_plan(
            original,
            payload,
            repeated_topic=repeated_topic,
            loop_level=loop_level,
        )

    return _search_plan(
        original,
        payload,
        reason,
        repeated_topic=repeated_topic,
        loop_level=loop_level,
    )
