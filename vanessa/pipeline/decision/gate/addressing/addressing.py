from vanessa.pipeline.decision.detectors.intent import IntentDetector, IntentResult
from vanessa.pipeline.decision.gate.addressing.addressing_rules import (
    has_direct_mention_or_reply,
    is_unaddressed_reply_to_other,
    open_question_warrants_reply,
)
from vanessa.pipeline.decision.gate.expectation.reply_expectation import (
    is_contextual_vocative_address,
    listen_window_warrants_reply,
    mention_warrants_reply,
)


def _soft_address(
    text: str,
    *,
    should_reply: bool | None,
    in_listen_window: bool,
    trigger_detected: bool,
    has_question: bool,
) -> bool:
    if should_reply is True:
        return True
    if is_contextual_vocative_address(text):
        return True
    # A question in an active conversation is a candidate for a reply even
    # without a mention — lets the bot actually answer contextually
    # addressed questions ("хочешь закурить?") that the decision engine
    # approved via an active session instead of downgrading them here.
    if open_question_warrants_reply(text, has_question=has_question):
        return True
    return _listen_window_address(
        text,
        should_reply=should_reply,
        in_listen_window=in_listen_window,
        trigger_detected=trigger_detected,
        has_question=has_question,
    )


def _listen_window_address(
    text: str,
    *,
    should_reply: bool | None,
    in_listen_window: bool,
    trigger_detected: bool,
    has_question: bool,
) -> bool:
    if not in_listen_window:
        return False
    return listen_window_warrants_reply(
        text,
        should_reply=should_reply,
        has_question=has_question,
        trigger_detected=trigger_detected,
    )


def is_addressed_to_bot(
    text: str,
    *,
    mentions_bot: bool = False,
    reply_to_bot: bool = False,
    reply_to_other_user: bool = False,
    should_reply: bool | None = None,
    in_listen_window: bool = False,
    trigger_detected: bool = False,
    intent: IntentResult | None = None,
) -> bool:
    if is_unaddressed_reply_to_other(
        mentions_bot=mentions_bot,
        reply_to_bot=reply_to_bot,
        reply_to_other_user=reply_to_other_user,
    ):
        return False

    detected = intent if intent is not None else IntentDetector().detect(text)

    if has_direct_mention_or_reply(
        mentions_bot=mentions_bot,
        reply_to_bot=reply_to_bot,
        detected_mentions_bot=detected.mentions_bot,
    ):
        return mention_warrants_reply(
            text,
            should_reply=should_reply,
            reply_to_bot=reply_to_bot,
        )

    return _soft_address(
        text,
        should_reply=should_reply,
        in_listen_window=in_listen_window,
        trigger_detected=trigger_detected,
        has_question=detected.has_question,
    )
