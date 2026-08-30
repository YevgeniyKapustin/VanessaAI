from vanessa.pipeline.decision.detectors.intent import IntentDetector, IntentResult
from vanessa.pipeline.decision.gate.reply_expectation import (
    is_contextual_vocative_address,
    is_conversation_closure,
    is_third_party_about_bot,
    is_unsolicited_remark,
    listen_window_warrants_reply,
    mention_warrants_reply,
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
    if reply_to_other_user and not mentions_bot and not reply_to_bot:
        return False

    detected = intent if intent is not None else IntentDetector().detect(text)

    if mentions_bot or reply_to_bot or detected.mentions_bot:
        return mention_warrants_reply(
            text,
            should_reply=should_reply,
            reply_to_bot=reply_to_bot,
        )

    if should_reply is True:
        return True

    if is_contextual_vocative_address(text):
        return True

    if detected.has_question and not (
        is_conversation_closure(text)
        or is_unsolicited_remark(text)
        or is_third_party_about_bot(text)
    ):
        # A question in an active conversation is a candidate for a reply even
        # without a mention — lets the bot actually answer contextually
        # addressed questions ("хочешь закурить?") that the decision engine
        # approved via an active session instead of downgrading them here.
        return True

    return in_listen_window and listen_window_warrants_reply(
        text,
        should_reply=should_reply,
        has_question=detected.has_question,
        trigger_detected=trigger_detected,
    )
