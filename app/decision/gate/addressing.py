from app.decision.detectors.intent import IntentDetector, IntentResult


def is_addressed_to_bot(
    text: str,
    *,
    mentions_bot: bool = False,
    reply_to_bot: bool = False,
    intent: IntentResult | None = None,
) -> bool:
    if mentions_bot or reply_to_bot:
        return True
    detected = intent if intent is not None else IntentDetector().detect(text)
    return detected.mentions_bot
