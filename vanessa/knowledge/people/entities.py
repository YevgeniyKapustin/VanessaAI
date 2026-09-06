"""Deterministic participant-mention resolution for context filtering.

The query-composition path historically dumped ALL chat participants (up to
``knowledge_participant_max_people`` x several facts) into every planner prompt,
and the semantic retriever only ever fetched ONE person dossier regardless of
how many people a message mentioned. This module deterministically scans the
current message + the recent window for People-card aliases and returns the
matched card files, so:

- the participants digest injects only mentioned / recently-active people;
- the semantic retriever can pull EVERY mentioned dossier (multi-person),
  bounded, instead of a single arbitrary one.

Mention detection is a cheap exact-alias scan (word-boundary guarded), NOT an
LLM call. It complements the LLM turn planner: the planner decides *whether*
the archive is needed and with what detail; the resolver decides *which*
people cards are relevant.
"""

from __future__ import annotations

import re

from vanessa.config.content import get_question_words
from vanessa.core.messages import ContextMessage
from vanessa.knowledge.people.entity_mentions import (
    mentioned_people_in_text,
    normalize_mention,
    people_file_for_name,
)

# Explicit "about person X" phrasing (not a bare question): «расскажи про
# крабера», «что там у лича», «как у лича с работой», «кто такой тик так».
_PERSON_PROMPT_RE = re.compile(
    r"(?:расскажи|как\s+у|что\s+там\s+у|что\s+с|кто\s+такой|про\s+|об\s+)",
    re.IGNORECASE,
)

# First-person "about ME (the sender)", never the bot: «расскажи про меня»,
# «кто я», «обо мне». «про себя» is the bot and must not match here.
_SELF_PERSON_RE = re.compile(
    r"(?:\bпро\s+меня\b|\bобо\s+мне\b|\bкто\s+я\b|"
    r"\bкак(?:ой|ая|ое|ие)\s+я\b)",
    re.IGNORECASE,
)

__all__ = [
    "is_person_focused",
    "is_self_person_query",
    "mentioned_people_in_text",
    "people_file_for_name",
    "resolve_mentioned_people",
]


def _question_pattern() -> re.Pattern:
    """Regex over the configured question words (config/content/decision.yaml)."""
    words = sorted(
        {str(word).strip().lower() for word in get_question_words() if str(word).strip()},
        key=len,
        reverse=True,
    )
    if not words:
        return re.compile(r"(?!x)x")
    joined = "|".join(re.escape(word) for word in words)
    return re.compile(rf"(?:^|\s)(?:{joined})\b", re.IGNORECASE)


def is_self_person_query(text: str) -> bool:
    """True when the user asks about themselves, not about Vanessa."""
    normalized = normalize_mention(text)
    if not normalized:
        return False
    return bool(_SELF_PERSON_RE.search(normalized))


def _extend_unique(result: list[str], seen: set[str], files: list[str]) -> None:
    for file in files:
        if file not in seen:
            seen.add(file)
            result.append(file)


def _scan_recent_people(
    recent_messages: list[ContextMessage] | None,
    people_index: dict,
    recent_window: int,
    seen: set[str],
    result: list[str],
) -> None:
    recent = recent_messages or []
    window = recent[-recent_window:] if recent_window > 0 else []
    for msg in window:
        text = str(getattr(msg, "content", "") or "")
        reply = getattr(msg, "reply_to_text", None)
        if reply:
            text += " " + str(reply or "")
        _extend_unique(result, seen, mentioned_people_in_text(text, people_index))


def resolve_mentioned_people(
    message: str,
    recent_messages: list[ContextMessage] | None,
    people_index: dict,
    *,
    recent_window: int = 5,
    sender_name: str = "",
) -> list[str]:
    """People mentioned in the current message, then in the recent window.

    The current message is the strongest signal and always comes first; the
    recent window (conversation continuation, per the sliding-window scheme)
    only fills in people not already named. ``recent_window <= 0`` disables the
    window scan. A first-person «про меня» prepends the sender's card.
    """
    result: list[str] = []
    seen: set[str] = set()
    if sender_name and is_self_person_query(message or ""):
        self_file = people_file_for_name(sender_name, people_index)
        if self_file:
            seen.add(self_file)
            result.append(self_file)
    _extend_unique(
        result, seen, mentioned_people_in_text(message or "", people_index)
    )
    _scan_recent_people(recent_messages, people_index, recent_window, seen, result)
    return result


def is_person_focused(text: str) -> bool:
    """True when the message is *about* a person, not a passing name drop.

    A message is person-focused when it asks a question (configured question
    words) or explicitly prompts for a person («расскажи про X», «что там у
    X», «кто такой X»). Used by the retrieve stage to decide whether the
    deterministic resolver may force People retrieval even when the planner
    omitted the ``people`` knowledge index.
    """
    normalized = normalize_mention(text)
    if not normalized:
        return False
    if is_self_person_query(normalized):
        return True
    if _question_pattern().search(normalized):
        return True
    return bool(_PERSON_PROMPT_RE.search(normalized))
