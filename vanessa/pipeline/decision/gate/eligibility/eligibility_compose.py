from vanessa.pipeline.decision.context import DecisionContext
from vanessa.pipeline.decision.detectors.intent import IntentResult
from vanessa.pipeline.decision.gate.addressing.addressing import is_addressed_to_bot
from vanessa.pipeline.decision.protocols import IntentDetectorProtocol
from vanessa.pipeline.decision.repeated_question import is_repeated_message


def _filled_intent(context: DecisionContext) -> IntentResult | None:
    intent = context.intent
    if intent.detected or intent.has_question or intent.mentions_bot:
        return intent
    return None


def _intent_or_detect(
    context: DecisionContext,
    intent_detector: IntentDetectorProtocol,
) -> IntentResult:
    filled = _filled_intent(context)
    if filled is not None:
        return filled
    return intent_detector.detect(context.text)


def _is_unaddressed_side_reply(context: DecisionContext) -> bool:
    return (
        context.reply_to_other_user
        and not context.mentions_bot
        and not context.reply_to_bot
    )


def _is_directly_addressed(
    context: DecisionContext,
    detected: IntentResult,
) -> bool:
    return context.mentions_bot or context.reply_to_bot or detected.mentions_bot


def _blocks_repeated_planner_veto(context: DecisionContext) -> bool:
    # A repeated message is junk even when it mentions the bot — the
    # deterministic repeat detector must win over the direct-address
    # override (otherwise a spam burst that the planner vetoed as
    # «повтор» still composes a reply).
    if context.should_reply is not False:
        return False
    if not context.recent_messages:
        return False
    return is_repeated_message(
        context.text,
        context.recent_messages,
        sender_telegram_id=context.sender_telegram_id,
    )


def _blocks_unaddressed_planner_veto(
    context: DecisionContext,
    *,
    intent_detector: IntentDetectorProtocol,
) -> bool:
    # A planner veto normally closes the thread, but a deterministic
    # direct address overrides it: the LLM planner can misclassify a
    # clear "ванесса + императив" as self-talk («общение между
    # собой»), while the deterministic intent layer knows the bot was
    # addressed. Only honor the veto for non-addressed messages — for
    # an addressed one fall through to the addressing check below.
    if context.should_reply is not False:
        return False
    detected = _intent_or_detect(context, intent_detector)
    return not _is_directly_addressed(context, detected)


def allows_compose(
    context: DecisionContext,
    *,
    humor_ok: bool = False,
) -> bool:
    if humor_ok:
        return True
    return is_addressed_to_bot(
        context.text,
        mentions_bot=context.mentions_bot,
        reply_to_bot=context.reply_to_bot,
        reply_to_other_user=context.reply_to_other_user,
        should_reply=context.should_reply,
        in_listen_window=context.in_listen_window,
        trigger_detected=context.trigger.detected,
        intent=_filled_intent(context),
    )


def _hard_block_compose(
    context: DecisionContext,
    intent_detector: IntentDetectorProtocol,
) -> bool:
    if _is_unaddressed_side_reply(context):
        return True
    if _blocks_repeated_planner_veto(context):
        return True
    return _blocks_unaddressed_planner_veto(context, intent_detector=intent_detector)


def should_block_compose(
    context: DecisionContext,
    *,
    intent_detector: IntentDetectorProtocol,
    humor_ok: bool = False,
) -> bool:
    if humor_ok:
        return False
    if _hard_block_compose(context, intent_detector):
        return True
    if context.in_listen_window:
        return False
    return not allows_compose(context)
