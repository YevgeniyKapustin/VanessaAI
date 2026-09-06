"""Compose-prompt budget: per-section and global char caps.

``PromptBuilder`` concatenates several context sections — old history, semantic
knowledge blocks, the recent session, humor quotes, memes, metrics. Without a
cap, a bloated retrieval can blow the LLM context window and dilute attention.
This module applies two guards:

- per-section caps (each section body is truncated to its configured limit,
  cutting at a sentence/line boundary so the text never ends mid-sentence);
- a global cap over the whole user prompt, trimming the lowest-priority
  sections first while the current message and short directives always survive.

Priority order (highest survives first): current message > directives >
reply-to > knowledge > web > session > context > metrics > humor > memes.
"""

from __future__ import annotations

from vanessa.config.content import PromptBudgetContent
from vanessa.infrastructure.observability.metrics import (
    record_prompt_budget,
    record_prompt_truncation,
)

# Priority of a section in the prompt; higher survives truncation.
PRIORITY_CURRENT = 100
PRIORITY_DIRECTIVES = 95
PRIORITY_REPLY = 90
PRIORITY_KNOWLEDGE = 80
# Live web-search results sit just below the archive: fresh, external facts are
# valuable for the answer but less authoritative than the bot's own memory.
PRIORITY_WEB = 78
PRIORITY_SESSION = 70
PRIORITY_CONTEXT = 60
PRIORITY_METRICS = 45
PRIORITY_HUMOR = 50
PRIORITY_MEME = 40
PRIORITY_MEME_MENU = 30

# A budgeted part: (priority, section name, body). ``section`` names match
# PromptBudgetContent fields so per-section caps are looked up generically.
BudgetPart = tuple[int, str, str]


def truncate_body(text: str, limit: int) -> str:
    """Trim ``text`` to at most ``limit`` chars, at a sentence/line boundary.

    ``limit <= 0`` means "no limit" and returns the text unchanged. The cut
    prefers a ``. `` / ``.\n`` sentence boundary, then a newline, so the model
    never sees a mid-sentence break; otherwise the head is kept and capped with
    an ellipsis.
    """
    if limit <= 0 or len(text) <= limit:
        return text
    # Reserve one char for the ellipsis so the result never exceeds ``limit``.
    head = text[: limit - 1]
    for boundary in (head.rfind(". "), head.rfind(".\n"), head.rfind("\n")):
        if boundary >= limit // 2 - 1:
            return head[: boundary + 1].rstrip() + "…"
    return head.rstrip() + "…"


def _section_cap(budget: PromptBudgetContent, section: str) -> int:
    value = getattr(budget, section, 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _budget_inactive(*, enabled: bool, budget: PromptBudgetContent | None) -> bool:
    return not enabled or budget is None


def _trim_section(
    priority: int,
    section: str,
    body: str,
    budget: PromptBudgetContent,
) -> BudgetPart | None:
    cap = _section_cap(budget, section)
    trimmed = body
    if cap > 0 and len(body) > cap:
        trimmed = truncate_body(body, cap)
    if not trimmed.strip():
        return None
    return (priority, section, trimmed)


def _apply_section_caps(
    parts: list[BudgetPart],
    budget: PromptBudgetContent,
) -> list[BudgetPart]:
    result: list[BudgetPart] = []
    for priority, section, body in parts:
        trimmed = _trim_section(priority, section, body, budget)
        if trimmed is not None:
            result.append(trimmed)
    return result


def _apply_global_cap(
    result: list[BudgetPart],
    budget: PromptBudgetContent,
) -> list[BudgetPart]:
    if budget.max_chars > 0:
        return _enforce_global_cap(result, budget.max_chars)
    return result


def _record_kept_sections(result: list[BudgetPart], *, record: bool) -> None:
    if not record:
        return
    for _, section, body in result:
        record_prompt_budget(section, len(body))


def apply_budget(
    parts: list[BudgetPart],
    budget: PromptBudgetContent,
    *,
    enabled: bool,
    record: bool = True,
) -> list[BudgetPart]:
    """Apply per-section caps + the global cap; returns parts in original order.

    When ``record`` is true, each kept section's final length and every
    truncation are reported to the observability metrics.
    """
    if _budget_inactive(enabled=enabled, budget=budget):
        return parts

    result = _apply_section_caps(parts, budget)
    result = _apply_global_cap(result, budget)
    _record_kept_sections(result, record=record)
    return result


def _claim_chars(length: int, remaining: int) -> tuple[int, int]:
    if remaining <= 0:
        return 0, remaining
    take = min(length, remaining)
    return take, remaining - take


def _allocate_keep(parts: list[BudgetPart], max_chars: int) -> dict[int, int]:
    keep: dict[int, int] = {}
    remaining = max_chars
    ranked = sorted(
        enumerate(parts), key=lambda pair: pair[1][0], reverse=True
    )
    for idx, (_priority, _, body) in ranked:
        take, remaining = _claim_chars(len(body), remaining)
        keep[idx] = take
    return keep


def _kept_body(section: str, body: str, take: int) -> str | None:
    if take <= 0:
        record_prompt_truncation(section)
        return None
    trimmed = body
    if take < len(body):
        trimmed = truncate_body(body, take)
        record_prompt_truncation(section)
    if not trimmed.strip():
        return None
    return trimmed


def _apply_allocation(
    parts: list[BudgetPart],
    keep: dict[int, int],
) -> list[BudgetPart]:
    result: list[BudgetPart] = []
    for idx, (priority, section, body) in enumerate(parts):
        trimmed = _kept_body(section, body, keep[idx])
        if trimmed is None:
            continue
        result.append((priority, section, trimmed))
    return result


def _enforce_global_cap(parts: list[BudgetPart], max_chars: int) -> list[BudgetPart]:
    """Trim the lowest-priority sections until the total fits ``max_chars``."""
    total = sum(len(body) for _, _, body in parts)
    if total <= max_chars:
        return parts

    # Allocate the budget from the highest priority down; when it runs out
    # mid-section, that section is truncated and everything lower is dropped.
    keep = _allocate_keep(parts, max_chars)
    return _apply_allocation(parts, keep)
