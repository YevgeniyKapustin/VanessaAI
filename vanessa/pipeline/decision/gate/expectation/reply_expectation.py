import re

from vanessa.core.messages import ContextMessage
from vanessa.core.session import is_dismissal_request
from vanessa.pipeline.decision.gate.expectation.reply_expectation_patterns import (
    BOT_PRONOUN_REPLY,
    CLOSURE_RE,
    GROUP_REMARK_RE,
    IMPERATIVE_START,
    THIRD_PARTY_BOT_RE,
    VOCATIVE_COMMA,
)

__all__ = [
    "expects_follow_up_after_bot",
    "is_bot_pronoun_reply",
    "is_contextual_vocative_address",
    "is_conversation_closure",
    "is_dismissal_request",
    "is_third_party_about_bot",
    "is_unsolicited_remark",
    "last_prior_role",
    "listen_window_warrants_reply",
    "mention_warrants_reply",
]


def is_conversation_closure(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return True
    return bool(CLOSURE_RE.search(normalized))


def is_unsolicited_remark(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if "?" in normalized:
        return False
    return bool(GROUP_REMARK_RE.search(normalized))


def is_third_party_about_bot(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if re.search(r"\b(ванесса|vanessa)\b", normalized, re.IGNORECASE):
        return False
    return bool(THIRD_PARTY_BOT_RE.search(normalized))


def _vocative_candidate(normalized: str) -> bool:
    if is_unsolicited_remark(normalized):
        return False
    if is_third_party_about_bot(normalized):
        return False
    if IMPERATIVE_START.search(normalized):
        return True
    return bool(VOCATIVE_COMMA.search(normalized))


def is_contextual_vocative_address(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    return _vocative_candidate(normalized)


def _mention_expects_reply(text: str) -> bool:
    if is_conversation_closure(text):
        return False
    if is_unsolicited_remark(text):
        return False
    return not is_third_party_about_bot(text)


def mention_warrants_reply(
    text: str,
    *,
    should_reply: bool | None = None,
    reply_to_bot: bool = False,
) -> bool:
    """Whether a message that mentions the bot implies the sender expects a reply.

    A direct mention (name/alias/mention entity) normally warrants a reply.
    It does not when the message is clearly not directed at the bot: a status
    remark, an unsolicited group observation, third-party talk about the bot,
    or a conversation closer. A direct reply to the bot or an explicit planner
    go-ahead always warrants a reply.
    """
    if reply_to_bot:
        return True
    if should_reply is True:
        return True
    return _mention_expects_reply(text)


def is_bot_pronoun_reply(text: str) -> bool:
    normalized = text.strip()
    if not normalized or is_third_party_about_bot(normalized):
        return False
    return bool(BOT_PRONOUN_REPLY.search(normalized))


_MIN_PRIOR_MESSAGES = 2
_MIN_FOLLOW_UP_WORDS = 3


def last_prior_role(messages: list[ContextMessage]) -> str | None:
    if len(messages) < _MIN_PRIOR_MESSAGES:
        return None
    return messages[-2].role


def _listen_window_blocked(text: str, *, should_reply: bool | None) -> bool:
    if is_unsolicited_remark(text) or is_third_party_about_bot(text):
        return True
    return should_reply is False


def _listen_window_signal(
    *,
    should_reply: bool | None,
    has_question: bool,
    trigger_detected: bool,
) -> bool:
    if should_reply is True:
        return True
    if trigger_detected:
        return True
    return has_question


def _listen_window_positive(
    text: str,
    *,
    should_reply: bool | None,
    has_question: bool,
    trigger_detected: bool,
) -> bool:
    if _listen_window_signal(
        should_reply=should_reply,
        has_question=has_question,
        trigger_detected=trigger_detected,
    ):
        return True
    if is_bot_pronoun_reply(text):
        return True
    if is_contextual_vocative_address(text):
        return True
    # Inside the post-reply window a substantive message that continues the
    # thread (not noise/closure/unsolicited/third-party) is a candidate: the
    # bot participates in the dialogue unless the planner vetoed a reply.
    return True


def listen_window_warrants_reply(
    text: str,
    *,
    should_reply: bool | None,
    has_question: bool,
    trigger_detected: bool,
) -> bool:
    if _listen_window_blocked(text, should_reply=should_reply):
        return False
    return _listen_window_positive(
        text,
        should_reply=should_reply,
        has_question=has_question,
        trigger_detected=trigger_detected,
    )


def _follow_up_blocked(text: str) -> bool:
    if is_conversation_closure(text) or is_unsolicited_remark(text):
        return True
    return is_third_party_about_bot(text)


def expects_follow_up_after_bot(text: str, *, last_prior_role: str | None) -> bool:
    if last_prior_role != "assistant":
        return False
    if _follow_up_blocked(text):
        return False
    normalized = text.strip()
    if "?" in normalized:
        return True
    return len(normalized.split()) >= _MIN_FOLLOW_UP_WORDS
