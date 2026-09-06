from __future__ import annotations

from vanessa.pipeline.decision.turn_plan import TurnPlan

_TONE_VALUES = frozenset({"neutral", "serious", "ironic", "humorous"})
_DETAIL_VALUES = frozenset({"brief", "normal", "detailed"})


def _parse_tone(value: object) -> str:
    if not isinstance(value, str):
        return "neutral"
    tone = value.strip().lower()
    return tone if tone in _TONE_VALUES else "neutral"


def _parse_detail(value: object) -> str:
    if not isinstance(value, str):
        return "normal"
    detail = value.strip().lower()
    return detail if detail in _DETAIL_VALUES else "normal"


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _parse_should_reply_str(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"true", "yes", "да", "1"}:
        return True
    if normalized in {"false", "no", "нет", "0"}:
        return False
    return None


def _parse_should_reply(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return None
    return _parse_should_reply_str(value)


def _skip_plan(
    original: str,
    payload: dict,
    reason: str,
    *,
    repeated_topic: bool,
    loop_level: int,
) -> TurnPlan:
    return TurnPlan(
        original=original,
        text="",
        skip_search=True,
        should_reply=False,
        repeated_topic=repeated_topic,
        loop_level=loop_level,
        detail=_parse_detail(payload.get("detail")),
        reason=reason,
    )


def _clarification_plan(
    original: str,
    payload: dict,
    *,
    repeated_topic: bool,
    loop_level: int,
) -> TurnPlan:
    # The user's message references something without context — reply with
    # a short clarifying question, not a full answer. There is nothing
    # meaningful to search for.
    clarification_hint = str(payload.get("clarification_hint", "")).strip()
    return TurnPlan(
        original=original,
        text="",
        skip_search=True,
        tone=_parse_tone(payload.get("tone")),
        should_reply=True,
        needs_clarification=True,
        clarification_hint=clarification_hint,
        detail=_parse_detail(payload.get("detail")),
        repeated_topic=repeated_topic,
        loop_level=loop_level,
    )


def _humor_fields(payload: dict) -> tuple[bool, str]:
    humor_ok = payload.get("humor_ok") is True
    humor_query = str(payload.get("humor_query", "")).strip()
    if humor_ok and not humor_query:
        humor_ok = False
    return humor_ok, humor_query if humor_ok else ""


def _web_search_fields(payload: dict, text: str) -> tuple[bool, str]:
    # Live web search: the planner flags it when the question needs fresh /
    # external data. ``web_query`` is the search query; when the planner
    # forgot it, fall back to the composed search_query so the search never
    # runs on an empty string.
    web_search = payload.get("web_search") is True
    web_query = str(payload.get("web_query", "")).strip()
    if web_search and not web_query:
        web_query = text
    web_search = web_search and bool(web_query)
    return web_search, web_query


def _search_plan(
    original: str,
    payload: dict,
    reason: str,
    *,
    repeated_topic: bool,
    loop_level: int,
) -> TurnPlan:
    text = str(payload.get("search_query", "")).strip()
    humor_ok, humor_query = _humor_fields(payload)
    web_search, web_query = _web_search_fields(payload, text)
    knowledge_indexes = tuple(
        str(item).strip().lower()
        for item in _as_list(payload.get("knowledge_indexes"))
        if str(item).strip()
    )
    return TurnPlan(
        original=original,
        text=text,
        skip_search=not text,
        tone=_parse_tone(payload.get("tone")),
        humor_ok=humor_ok,
        humor_query=humor_query,
        should_reply=_parse_should_reply(payload.get("should_reply")),
        deep_search=payload.get("deep_search") is True,
        knowledge_indexes=knowledge_indexes,
        knowledge_query=str(payload.get("knowledge_query", "")).strip(),
        knowledge_detail=payload.get("knowledge_detail") is True,
        web_search=web_search,
        web_query=web_query,
        uses_pro_model=payload.get("uses_pro_model") is True,
        repeated_topic=repeated_topic,
        loop_level=loop_level,
        detail=_parse_detail(payload.get("detail")),
        reason=reason,
    )
