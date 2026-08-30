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
    if not enabled or budget is None:
        return parts

    result: list[BudgetPart] = []
    for priority, section, body in parts:
        cap = _section_cap(budget, section)
        if cap > 0 and len(body) > cap:
            body = truncate_body(body, cap)
        if body.strip():
            result.append((priority, section, body))

    if budget.max_chars > 0:
        result = _enforce_global_cap(result, budget.max_chars)

    if record:
        from vanessa.observability.metrics import record_prompt_budget

        for _, section, body in result:
            record_prompt_budget(section, len(body))
    return result


def _enforce_global_cap(parts: list[BudgetPart], max_chars: int) -> list[BudgetPart]:
    """Trim the lowest-priority sections until the total fits ``max_chars``."""
    total = sum(len(body) for _, _, body in parts)
    if total <= max_chars:
        return parts

    # Allocate the budget from the highest priority down; when it runs out
    # mid-section, that section is truncated and everything lower is dropped.
    keep: dict[int, int] = {}
    remaining = max_chars
    for idx, (priority, _, body) in sorted(
        enumerate(parts), key=lambda pair: pair[1][0], reverse=True
    ):
        if remaining <= 0:
            keep[idx] = 0
            continue
        take = min(len(body), remaining)
        keep[idx] = take
        remaining -= take

    from vanessa.observability.metrics import record_prompt_truncation

    result: list[BudgetPart] = []
    for idx, (priority, section, body) in enumerate(parts):
        take = keep[idx]
        if take <= 0:
            record_prompt_truncation(section)
            continue
        if take < len(body):
            body = truncate_body(body, take)
            record_prompt_truncation(section)
        if body.strip():
            result.append((priority, section, body))
    return result
