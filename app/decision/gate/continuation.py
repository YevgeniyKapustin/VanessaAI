"""Sender-aware "continuation demand" detection.

A short follow-up phrase right after the bot's own reply ("а ещё" = "tell me
another one") is an explicit request even though it carries none of the usual
deterministic signals (no bot name, no ``?``, no trigger/modal verb). Without
this, such terse follow-ups are only saved by the post-reply listen window;
once that window is missed (other people wrote in between, or the message
count exceeded ``post_reply_listen_count``), the planner prefilter drops them
as ``side_talk`` and the reaction gate's LLM tier frequently answers NO.

To keep false positives low the detection is deliberately narrow: the message
must be a short continuation phrase AND the sender must be the same user the
bot just answered (the one immediately before the last assistant message).
"""

from __future__ import annotations

from app.core.messages import ContextMessage

__all__ = [
    "DEFAULT_CONTINUATION_PHRASES",
    "DEFAULT_MAX_MESSAGES_BACK",
    "is_continuation_phrase",
    "last_bot_reply_partner_sender_id",
    "is_sender_continuation_demand",
]

# Fallback phrase set, used when config/content/decision.yaml provides no
# ``continuation_phrases``. Full lowercase phrases, matched as a whole against
# the normalized (lowercased, whitespace-collapsed) message.
DEFAULT_CONTINUATION_PHRASES = (
    "а ещё",
    "и ещё",
    "ещё",
    "еще",
    "ещё один",
    "ещё раз",
    "ещё вариант",
    "давай ещё",
    "давай дальше",
    "ну и ещё",
    "продолжай",
    "продолжи",
    "расскажи ещё",
    "расскажи ещё один",
    "дальше",
    "что дальше",
    "а дальше",
    "а ещё что",
)

# A continuation phrase may carry a couple of extra words ("а ещё анекдот про
# программистов"), but not a full paragraph — that would be a real message.
_MAX_PHRASE_WORDS = 5
# How many messages back the bot's last reply may be and still count as "right
# after" (the listen window is 4, so this gives headroom for interleaved talk).
DEFAULT_MAX_MESSAGES_BACK = 6


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def is_continuation_phrase(
    text: str,
    phrases: tuple[str, ...] | None = None,
) -> bool:
    """Whether ``text`` is a short continuation/follow-up demand phrase."""
    normalized = _normalize(text)
    if not normalized:
        return False
    words = normalized.split()
    if len(words) > _MAX_PHRASE_WORDS:
        return False
    candidates = phrases if phrases else DEFAULT_CONTINUATION_PHRASES
    for phrase in candidates:
        candidate = _normalize(phrase)
        if not candidate:
            continue
        if normalized == candidate:
            return True
        # A short message that opens with a continuation phrase still reads as
        # a demand ("а ещё анекдот про программистов"); the global word-count
        # guard above already keeps full paragraphs out.
        if normalized.startswith(candidate):
            return True
    return False


def last_bot_reply_partner_sender_id(
    recent_messages: list[ContextMessage],
) -> int | None:
    """Sender of the user message the bot last answered (None if unknown).

    The bot's most recent reply is the last ``assistant`` message; the user
    message immediately before it is the one that prompted it.
    """
    for index in range(len(recent_messages) - 1, -1, -1):
        if recent_messages[index].role == "assistant":
            if index - 1 >= 0 and recent_messages[index - 1].role == "user":
                return recent_messages[index - 1].sender_telegram_id
            return None
    return None


def is_sender_continuation_demand(
    text: str,
    recent_messages: list[ContextMessage],
    sender_telegram_id: int | None,
    *,
    max_messages_back: int = DEFAULT_MAX_MESSAGES_BACK,
    phrases: tuple[str, ...] | None = None,
) -> bool:
    """Sender-aware continuation demand right after the bot's own reply."""
    if not sender_telegram_id:
        return False
    if not is_continuation_phrase(text, phrases=phrases):
        return False
    assistant_index: int | None = None
    for index in range(len(recent_messages) - 1, -1, -1):
        if recent_messages[index].role == "assistant":
            assistant_index = index
            break
    if assistant_index is None:
        return False
    if len(recent_messages) - 1 - assistant_index > max_messages_back:
        return False
    partner = last_bot_reply_partner_sender_id(recent_messages)
    return partner is not None and partner == sender_telegram_id
