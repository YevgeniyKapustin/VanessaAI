from vanessa.pipeline.decision.context import DecisionContext
from vanessa.pipeline.decision.detectors.intent import IntentResult
from vanessa.pipeline.decision.gate.addressing.quote_echo import is_recursive_quote_loop
from vanessa.pipeline.decision.gate.eligibility.eligibility_types import (
    HardIgnoreResult,
)
from vanessa.pipeline.decision.gate.eligibility.ignore_registry_protocol import (
    ChatIgnoreRegistryProtocol,
)
from vanessa.pipeline.decision.gate.expectation.reply_expectation import (
    is_dismissal_request,
    is_third_party_about_bot,
)
from vanessa.pipeline.decision.models import DecisionReason
from vanessa.pipeline.decision.protocols import IntentDetectorProtocol


def _resolved_intent(
    context: DecisionContext,
    intent_detector: IntentDetectorProtocol,
) -> IntentResult:
    intent = context.intent
    if intent.detected or intent.has_question or intent.mentions_bot:
        return intent
    return intent_detector.detect(context.text)


def _ignored_user_result(
    context: DecisionContext,
    ignore_registry: ChatIgnoreRegistryProtocol,
) -> HardIgnoreResult | None:
    if not context.telegram_chat_id or not context.sender_telegram_id:
        return None
    if not ignore_registry.is_ignored(
        context.telegram_chat_id,
        context.sender_telegram_id,
    ):
        return None
    return HardIgnoreResult("ignored_user", DecisionReason.USER_IGNORED)


def _unaddressed_third_party(
    text: str,
    *,
    directly_addressed: bool,
) -> bool:
    return is_third_party_about_bot(text) and not directly_addressed


def _unaddressed_reply_to_other(
    context: DecisionContext,
    *,
    directly_addressed: bool,
    detected_mentions_bot: bool,
) -> bool:
    return (
        context.reply_to_other_user
        and not directly_addressed
        and not detected_mentions_bot
    )


def _directly_addressed(context: DecisionContext) -> bool:
    return context.mentions_bot or context.reply_to_bot


def _unaddressed_side_talk(
    context: DecisionContext,
    *,
    directly_addressed: bool,
    detected_mentions_bot: bool,
) -> HardIgnoreResult | None:
    if _unaddressed_third_party(
        context.text,
        directly_addressed=directly_addressed,
    ):
        return HardIgnoreResult("side_talk", DecisionReason.NOT_EXPECTED)
    if _unaddressed_reply_to_other(
        context,
        directly_addressed=directly_addressed,
        detected_mentions_bot=detected_mentions_bot,
    ):
        return HardIgnoreResult("side_talk", DecisionReason.NOT_EXPECTED)
    return None


def hard_ignore(
    context: DecisionContext,
    *,
    intent_detector: IntentDetectorProtocol,
    ignore_registry: ChatIgnoreRegistryProtocol,
) -> HardIgnoreResult | None:
    detected = _resolved_intent(context, intent_detector)
    directly_addressed = _directly_addressed(context)

    ignored = _ignored_user_result(context, ignore_registry)
    if ignored is not None:
        return ignored

    if is_dismissal_request(context.text):
        return HardIgnoreResult("dismissal", DecisionReason.DISMISSAL)

    if is_recursive_quote_loop(
        context.text,
        context.recent_messages,
        reply_to_bot=context.reply_to_bot,
    ):
        return HardIgnoreResult("quote_echo", DecisionReason.QUOTE_ECHO)

    return _unaddressed_side_talk(
        context,
        directly_addressed=directly_addressed,
        detected_mentions_bot=detected.mentions_bot,
    )
