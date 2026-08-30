"""Deterministic memory prefilter: decide whether a transcript is worth an LLM pass.

The memory extraction LLM (``MemoryPlanner``) is expensive and mostly returns an
empty ``updates`` list on mundane chat. Before spending tokens we run a cheap,
fully deterministic heuristic over the *new* messages and skip the LLM when there
is nothing durable to remember. The heuristic is intentionally conservative: it
must never block genuinely memorable content (quotes, facts, recommendations),
only save the common case where a few short/reactionary messages carry no facts.
"""

from __future__ import annotations

import re

from vanessa.core.messages import ContextMessage

# A user message is "contentful" when it carries at least this many characters of
# substance (whitespace-collapsed), i.e. it is more than a short reply / greeting.
_DEFAULT_MIN_CONTENT_CHARS = 40

# Quoted exact phrases (likely quote-worthy) usually start with «, " or a quote.
_QUOTE_RE = re.compile(r"^\s*[«\"“]")
# Numbers with a unit, prices, and URLs are concrete facts (amounts, links, dates).
_SPECIFICS_RE = re.compile(
    r"(?:\d{2,}\s*(?:к|тыс|млн|руб|₽|\$|€|гг|год|лет|мес|день|чел|ч|мин)\b)|https?://|\b\d{4}\b"
)
# First-person disclosure signals a self-fact («я переезжаю», «у меня собака»).
_DISCLOSURE_RE = re.compile(r"\b(?:я|у меня|мой|моя|моё|мне|мы|у нас)\b", re.IGNORECASE)


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def memory_potential_score(
    messages: list[ContextMessage],
    *,
    min_content_chars: int = _DEFAULT_MIN_CONTENT_CHARS,
) -> tuple[float, dict]:
    """Score how likely the transcript holds durable, memorable content.

    Returns ``(score, breakdown)``. ``breakdown`` exposes the individual signals
    so callers can log *why* a run was skipped. Pure and deterministic.
    """
    user_lengths: list[int] = []
    bot_lengths: list[int] = []
    has_quote = False
    has_specifics = False
    has_disclosure = False
    for message in messages:
        text = _collapse(message.content)
        if not text:
            continue
        if message.role == "assistant":
            bot_lengths.append(len(text))
            continue
        user_lengths.append(len(text))
        if _QUOTE_RE.match(text):
            has_quote = True
        if _SPECIFICS_RE.search(text):
            has_specifics = True
        if _DISCLOSURE_RE.search(text):
            has_disclosure = True

    contentful_user = [n for n in user_lengths if n >= min_content_chars]
    score = 0.0
    if len(contentful_user) >= 1:
        score += 1.0
    if len(contentful_user) >= 2:
        score += 1.0
    if contentful_user and max(contentful_user) >= 200:
        # A single long message can carry several facts (a story, a plan).
        score += 0.5
    if bot_lengths and max(bot_lengths) >= 200:
        # A substantive bot reply implies the exchange itself had substance.
        score += 0.5
    if has_quote:
        score += 0.3
    if has_specifics:
        score += 0.3
    if has_disclosure:
        score += 0.2

    breakdown = {
        "contentful_user": len(contentful_user),
        "max_user_len": max(user_lengths) if user_lengths else 0,
        "max_bot_len": max(bot_lengths) if bot_lengths else 0,
        "has_quote": has_quote,
        "has_specifics": has_specifics,
        "has_disclosure": has_disclosure,
    }
    return round(score, 3), breakdown


def should_extract_memory(
    messages: list[ContextMessage],
    *,
    min_messages: int = 1,
    min_content_chars: int = _DEFAULT_MIN_CONTENT_CHARS,
    score_threshold: float = 1.5,
) -> bool:
    """True when the transcript is worth a memory LLM pass.

    A transcript is skipped when it has fewer than ``min_messages`` user messages
    with real content or its ``memory_potential_score`` is below the threshold.
    """
    if not messages:
        return False
    user_messages = [m for m in messages if m.role != "assistant" and _collapse(m.content)]
    if len(user_messages) < min_messages:
        return False
    score, _ = memory_potential_score(messages, min_content_chars=min_content_chars)
    return score >= score_threshold
