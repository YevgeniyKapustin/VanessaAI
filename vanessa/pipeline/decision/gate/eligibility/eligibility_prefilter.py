from vanessa.core.session.chat_session_state import in_post_reply_listen_window
from vanessa.pipeline.decision.context import DecisionContext
from vanessa.pipeline.decision.gate.eligibility.eligibility_prefilter_checks import (
    prefilter_addressed,
    prefilter_continuation,
    prefilter_deferred_question,
    prefilter_follow_up,
    prefilter_listen_window,
    prefilter_noise_tail,
    prefilter_trigger,
)
from vanessa.pipeline.decision.gate.eligibility.eligibility_types import (
    PrefilterVerdict,
    _drop,
    _follows_bot,
)
from vanessa.pipeline.decision.gate.expectation.reply_expectation import (
    is_conversation_closure,
)
from vanessa.pipeline.decision.protocols import (
    NoiseFilterProtocol,
    TriggerCheckerProtocol,
)


def soft_prefilter(
    context: DecisionContext,
    *,
    triggers: TriggerCheckerProtocol,
    noise: NoiseFilterProtocol,
    post_reply_listen_count: int,
    post_reply_listen_idle_seconds: float,
    continuation_enabled: bool,
    continuation_phrases: tuple[str, ...],
    defer_questions: bool,
) -> PrefilterVerdict:
    text = context.text
    recent_messages = context.recent_messages
    directly_addressed = context.mentions_bot or context.reply_to_bot
    trigger = triggers.detect(text)
    follows_bot = _follows_bot(recent_messages)
    in_listen_window = in_post_reply_listen_window(
        recent_messages,
        max_messages=post_reply_listen_count,
        max_idle_seconds=post_reply_listen_idle_seconds,
    )
    for verdict in (
        prefilter_addressed(
            text,
            directly_addressed=directly_addressed,
            reply_to_bot=context.reply_to_bot,
            intent=context.intent,
        ),
        prefilter_continuation(
            text,
            recent_messages,
            context.sender_telegram_id,
            enabled=continuation_enabled,
            phrases=continuation_phrases,
        ),
        prefilter_listen_window(
            text,
            noise,
            in_listen_window=in_listen_window,
            trigger_detected=trigger.detected,
        ),
        prefilter_noise_tail(
            text,
            noise,
            trigger_detected=trigger.detected,
        ),
        _drop("closure") if is_conversation_closure(text) else None,
        prefilter_follow_up(
            text,
            noise,
            directly_addressed=directly_addressed,
            follows_bot=follows_bot,
            trigger_detected=trigger.detected,
            intent=context.intent,
        ),
        prefilter_trigger(
            directly_addressed=directly_addressed,
            follows_bot=follows_bot,
            trigger_detected=trigger.detected,
            mentions_bot=context.intent.mentions_bot,
        ),
        prefilter_deferred_question(
            recent_messages,
            intent=context.intent,
            defer_questions=defer_questions,
        ),
    ):
        if verdict is not None:
            return verdict
    return _drop("side_talk")
