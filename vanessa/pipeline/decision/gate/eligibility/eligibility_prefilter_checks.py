from vanessa.core.messages import ContextMessage
from vanessa.pipeline.decision.detectors.intent import IntentResult
from vanessa.pipeline.decision.gate.addressing.continuation import (
    is_sender_continuation_demand,
)
from vanessa.pipeline.decision.gate.eligibility.eligibility_types import (
    PrefilterVerdict,
    _allow,
    _drop,
    _thread_dismissed,
)
from vanessa.pipeline.decision.gate.expectation.reply_expectation import (
    is_conversation_closure,
    is_unsolicited_remark,
    mention_warrants_reply,
)
from vanessa.pipeline.decision.protocols import NoiseFilterProtocol


def prefilter_addressed(
    text: str,
    *,
    directly_addressed: bool,
    reply_to_bot: bool,
    intent: IntentResult,
) -> PrefilterVerdict | None:
    if not (directly_addressed or intent.mentions_bot):
        return None
    if not mention_warrants_reply(
        text,
        should_reply=None,
        reply_to_bot=reply_to_bot,
    ):
        return _drop("side_talk")
    return _allow("direct_address" if directly_addressed else "bot_name")


def prefilter_continuation(
    text: str,
    recent_messages: list[ContextMessage],
    sender_telegram_id: int,
    *,
    enabled: bool,
    phrases: tuple[str, ...],
) -> PrefilterVerdict | None:
    if not (
        enabled
        and is_sender_continuation_demand(
            text,
            recent_messages,
            sender_telegram_id,
            phrases=phrases,
        )
    ):
        return None
    return _allow("continuation")


def _listen_window_noise_drop(
    text: str,
    noise: NoiseFilterProtocol,
    *,
    trigger_detected: bool,
) -> PrefilterVerdict | None:
    if trigger_detected:
        return None
    if noise.is_definite_noise(text):
        return _drop("noise")
    return None


def _listen_window_drop(
    text: str,
    noise: NoiseFilterProtocol,
    *,
    trigger_detected: bool,
) -> PrefilterVerdict | None:
    noise_drop = _listen_window_noise_drop(
        text,
        noise,
        trigger_detected=trigger_detected,
    )
    if noise_drop is not None:
        return noise_drop
    if is_unsolicited_remark(text):
        return _drop("side_talk")
    if is_conversation_closure(text):
        return _drop("closure")
    return None


def prefilter_listen_window(
    text: str,
    noise: NoiseFilterProtocol,
    *,
    in_listen_window: bool,
    trigger_detected: bool,
) -> PrefilterVerdict | None:
    if not in_listen_window:
        return None
    dropped = _listen_window_drop(
        text,
        noise,
        trigger_detected=trigger_detected,
    )
    if dropped is not None:
        return dropped
    return _allow("listen_window")


def prefilter_noise_tail(
    text: str,
    noise: NoiseFilterProtocol,
    *,
    trigger_detected: bool,
) -> PrefilterVerdict | None:
    if not noise.is_noise(text) or trigger_detected:
        return None
    if noise.is_definite_noise(text):
        return _drop("noise")
    return _allow("short_maybe")


def prefilter_follow_up(
    text: str,
    noise: NoiseFilterProtocol,
    *,
    directly_addressed: bool,
    follows_bot: bool,
    trigger_detected: bool,
    intent: IntentResult,
) -> PrefilterVerdict | None:
    if not follows_bot or noise.is_noise(text):
        return None
    if directly_addressed or intent.mentions_bot or trigger_detected:
        return _allow("follow_up")
    if intent.has_question:
        return _allow("follow_up_question")
    return None


def prefilter_trigger(
    *,
    directly_addressed: bool,
    follows_bot: bool,
    trigger_detected: bool,
    mentions_bot: bool,
) -> PrefilterVerdict | None:
    if trigger_detected and (directly_addressed or mentions_bot or follows_bot):
        return _allow("trigger")
    return None


def prefilter_deferred_question(
    recent_messages: list[ContextMessage],
    *,
    intent: IntentResult,
    defer_questions: bool,
) -> PrefilterVerdict | None:
    if (
        defer_questions
        and intent.has_question
        and not _thread_dismissed(recent_messages)
    ):
        return _allow("question")
    return None
