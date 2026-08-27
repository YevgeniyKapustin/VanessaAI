from dataclasses import dataclass
from enum import StrEnum


class DecisionAction(StrEnum):
    REPLY = "reply"
    IGNORE = "ignore"


class DecisionReason(StrEnum):
    INTENT = "intent"
    FORCE_REPLY = "force_reply"
    RELEVANT = "relevant"
    ADDRESSING = "addressing"
    IGNORE = "ignore"
    NOISE = "noise"
    CONSECUTIVE = "consecutive"
    RATE_LIMITED = "rate_limited"
    NO_REPLY_NEEDED = "no_reply_needed"
    NOT_EXPECTED = "not_expected"
    PREFILTER = "prefilter"
    # The lightweight pre-planner Decision Gate (reaction classifier) said the
    # message does not require a bot reaction (people chatting among themselves).
    REACTION_GATE = "reaction_gate"
    LISTEN_WINDOW = "listen_window"
    DISMISSAL = "dismissal"
    QUOTE_ECHO = "quote_echo"
    USER_IGNORED = "user_ignored"
    TOXIC = "toxic"
    REPEATED = "repeated"


@dataclass(frozen=True, slots=True)
class DecisionResult:
    action: DecisionAction
    reason: DecisionReason
    relevance_score: float = 0.0
    intent_detected: bool = False
    trigger_detected: bool = False
    session_active: bool = False
