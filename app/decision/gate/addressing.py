from app.decision.detectors.intent import IntentDetector, IntentResult
from app.decision.gate.reply_expectation import (
    is_contextual_vocative_address,
    listen_window_warrants_reply,
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

    if mentions_bot or reply_to_bot:
        return True

    detected = intent if intent is not None else IntentDetector().detect(text)
    if detected.mentions_bot:
        return True

    if should_reply is True:
        return True

    if is_contextual_vocative_address(text):
        return True

    if in_listen_window and listen_window_warrants_reply(
        text,
        should_reply=should_reply,
        has_question=detected.has_question,
        trigger_detected=trigger_detected,
    ):
        return True

    return False
