from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.context import DecisionContext


def decision_context_from_pipeline(ctx: TurnPipelineContext) -> DecisionContext:
    assert ctx.session is not None
    plan = ctx.turn_plan
    return DecisionContext(
        text=ctx.turn.message,
        telegram_chat_id=ctx.turn.telegram_chat_id,
        recent_messages=ctx.recent,
        should_reply=None if plan is None else plan.should_reply,
        mentions_bot=ctx.turn.mentions_bot,
        reply_to_bot=ctx.turn.reply_to_bot,
        reply_to_other_user=ctx.turn.reply_to_other_user,
        in_listen_window=ctx.session.in_listen_window,
        sender_telegram_id=ctx.turn.sender_telegram_id,
        sender_metrics=ctx.sender_metrics,
        loop_strength=ctx.loop_strength,
        annoyance=ctx.annoyance,
    )
