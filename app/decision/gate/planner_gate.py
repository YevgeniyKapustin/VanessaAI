from app.decision.context import DecisionContext


def planner_affirms_reply(context: DecisionContext) -> bool:
    if context.should_reply is not True:
        return False
    if context.directly_addressed or context.intent.mentions_bot:
        return True
    if context.in_listen_window:
        return True
    if context.session_active and (
        context.intent.detected or context.trigger.detected
    ):
        return True
    return False
