from dataclasses import dataclass

from vanessa.core.messages import ContextMessage
from vanessa.pipeline.decision.gate.expectation.reply_expectation import (
    is_dismissal_request,
)
from vanessa.pipeline.decision.models import DecisionReason

_FOLLOW_BOT_MIN_MESSAGES = 2


@dataclass(frozen=True, slots=True)
class HardIgnoreResult:
    tag: str
    decision_reason: DecisionReason


@dataclass(frozen=True, slots=True)
class PrefilterVerdict:
    run_planner: bool
    reason: str = ""


def _allow(reason: str) -> PrefilterVerdict:
    return PrefilterVerdict(run_planner=True, reason=reason)


def _drop(reason: str) -> PrefilterVerdict:
    return PrefilterVerdict(run_planner=False, reason=reason)


def prefilter_tag_to_decision_reason(tag: str) -> DecisionReason:
    mapping = {
        "ignored_user": DecisionReason.USER_IGNORED,
        "dismissal": DecisionReason.DISMISSAL,
        "quote_echo": DecisionReason.QUOTE_ECHO,
        "side_talk": DecisionReason.PREFILTER,
        "noise": DecisionReason.PREFILTER,
        "closure": DecisionReason.PREFILTER,
    }
    return mapping.get(tag, DecisionReason.PREFILTER)


def _follows_bot(recent_messages: list[ContextMessage]) -> bool:
    if len(recent_messages) < _FOLLOW_BOT_MIN_MESSAGES:
        return False
    return recent_messages[-2].role == "assistant"


def _thread_dismissed(recent_messages: list[ContextMessage]) -> bool:
    """Whether the user dismissed the bot after the last assistant message.

    A dismissal ("хватит", "заткнись", ...) closes the thread: even a later
    question should not be deferred to the reaction gate.
    """
    for message in reversed(recent_messages):
        if message.role == "assistant":
            return False
        if message.role == "user" and is_dismissal_request(message.content):
            return True
    return False
