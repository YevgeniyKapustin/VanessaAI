from vanessa.pipeline.decision.context import DecisionContext


def planner_affirms_reply(context: DecisionContext) -> bool:
    if context.should_reply is not True:
        return False
    if context.directly_addressed or context.intent.mentions_bot:
        return True
    if context.in_listen_window:
        return True
    return context.session_active and (
        context.intent.detected or context.trigger.detected
    )
