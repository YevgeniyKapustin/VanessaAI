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
    PLANNER = "planner"
    DISMISSAL = "dismissal"
    QUOTE_ECHO = "quote_echo"
    USER_IGNORED = "user_ignored"
    TOXIC = "toxic"
    REPEATED = "repeated"
    # Another AI bot wrote a message that is not for Vanessa (bot side talk).
    BOT_PEER_SIDE = "bot_peer_side"
    # The bot-to-bot reply budget is used up (depth, cooldown or hourly cap).
    BOT_PEER_LIMIT = "bot_peer_limit"
    # Vanessa's attitude to the sender is critically low (loop-repetition
    # annoyance and/or a persistently low relationship) → even a weak / slightly
    # disliked message is ignored (maximal ignore tendency).
    LOW_ATTITUDE = "low_attitude"
    # Compose-stage silence: the model wrote [ignore], returned an empty reply,
    # or wrote no [answer] tag after the strict retry.
    MODEL_IGNORE = "model_ignore"
    EMPTY_REPLY = "empty_reply"
    UNTAGGED = "untagged"


@dataclass(frozen=True, slots=True)
class DecisionResult:
    action: DecisionAction
    reason: DecisionReason
    relevance_score: float = 0.0
    intent_detected: bool = False
    trigger_detected: bool = False
    session_active: bool = False
