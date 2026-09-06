"""One-line person summaries for the planner participants digest."""

from __future__ import annotations

import re

_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}\s*[:\-]\s*")
_FACT_CAP = 140


def _clip_fact(fact: str) -> str:
    if len(fact) <= _FACT_CAP:
        return fact
    return fact[: _FACT_CAP - 1].rstrip() + "…"


def _fact_from_line(stripped: str, *, in_section: bool) -> str | None:
    if not in_section or not stripped.startswith("- "):
        return None
    fact = _DATE_PREFIX.sub("", stripped[2:].strip()).strip()
    if not fact:
        return None
    return _clip_fact(fact)


def context_facts(body: str) -> list[str]:
    """Bullets under ``## Контекст жизни``, newest last, date stripped."""
    facts: list[str] = []
    in_section = False
    for raw in body.splitlines():
        stripped = raw.strip()
        if stripped.startswith("## "):
            in_section = stripped == "## Контекст жизни"
            continue
        fact = _fact_from_line(stripped, in_section=in_section)
        if fact:
            facts.append(fact)
    return facts


def _person_nickname(meta, relative_path) -> str:
    person_id = str(meta.get("id") or relative_path)
    return str(meta.get("nickname") or person_id)


def _alias_parts(aliases, nickname: str) -> list[str]:
    if not isinstance(aliases, list):
        return []
    return [
        str(alias).strip()
        for alias in aliases
        if str(alias).strip().lower() != nickname.lower()
    ]


def _alias_text(meta, nickname: str) -> str:
    parts = _alias_parts(meta.get("aliases"), nickname)
    if not parts:
        return ""
    return f" (также {', '.join(parts[:3])})"


def _mood_text(meta) -> str:
    mood = str(meta.get("mood") or "").strip()
    if not mood:
        return ""
    return f", настроение: {mood}"


def _facts_text(note, max_facts: int) -> str:
    facts = context_facts(note.body or "")[-max_facts:]
    if not facts:
        return ""
    return ". Факты: " + "; ".join(facts)


def format_person_line(note, max_facts: int) -> str:
    meta = note.meta or {}
    nickname = _person_nickname(meta, note.relative_path)
    return (
        f"{nickname}"
        f"{_alias_text(meta, nickname)}"
        f"{_mood_text(meta)}"
        f"{_facts_text(note, max_facts)}"
    )
