"""Truthiness coalescers so vault apply-handlers stay under McCabe."""

from __future__ import annotations

from vanessa.knowledge.memory.writer_merge import as_list


def first_str(*values: object) -> str:
    """``str(a or b or "")`` without stacking ``or`` in the caller."""
    for value in values:
        if value:
            return str(value)
    return ""


def stripped_text(*values: object) -> str:
    return first_str(*values).strip()


def note_body(existing: object) -> str:
    return existing.body if existing else ""


def list_or_default(raw: object, default: list) -> list:
    return as_list(raw) or default
