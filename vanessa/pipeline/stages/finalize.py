from vanessa.config.content import get_content
from vanessa.core.protocols import (
    MessageRepositoryProtocol,
    TurnMetricsProtocol,
)
from vanessa.core.session.channel_keys import dialogue_session_key, turn_channel
from vanessa.core.turn import ConversationTurnResult
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.models import DecisionAction
from vanessa.pipeline.decision.protocols import DecisionEngineProtocol
from vanessa.pipeline.llm.format.answer_tag import strip_control_tags
from vanessa.pipeline.llm.format.stray_tags import strip_stray_tags
from vanessa.pipeline.llm.memes import MemeDecider
from vanessa.pipeline.stages.finalize_delivery import (
    delivery_messages,
    marker_free_reply,
    photo_fields,
    sticker_from_reply,
)


class FinalizeStage:
    def __init__(
        self,
        messages: MessageRepositoryProtocol,
        decision_engine: DecisionEngineProtocol,
        metrics: TurnMetricsProtocol,
        *,
        meme_decider: MemeDecider | None = None,
    ) -> None:
        self._messages = messages
        self._decision = decision_engine
        self._metrics = metrics
        self._meme_decider = meme_decider

    async def skip(self, ctx: TurnPipelineContext, *, reason: str) -> None:
        """Finish the turn without a reply.

        Used when a later stage decides the user's message does not need a
        reply. The turn is recorded as ignored (no assistant message is
        created, no reply is registered).
        """
        ctx.result = ConversationTurnResult(
            action=DecisionAction.IGNORE.value,
            reason=reason,
            relevance_score=(
                ctx.decision.relevance_score if ctx.decision is not None else 0.0
            ),
        )
        self._metrics.record_turn(
            action=ctx.result.action,
            reason=ctx.result.reason,
            planner_skipped=ctx.planner_skipped,
        )

    async def run(self, ctx: TurnPipelineContext) -> bool:
        assert ctx.user_msg is not None
        assert ctx.decision is not None
        assert ctx.turn_plan is not None
        assert ctx.reply is not None

        clean_reply, sticker_tag = sticker_from_reply(ctx, ctx.reply)
        # Final control-tag safety net: a reasoning model may emit [answer] /
        # <answer> / [ignore] in a form the provider's splitter missed — never
        # let a control tag reach the chat. The [next] block marker is left for
        # the block splitter below, which needs it to separate the messages.
        clean_reply = strip_control_tags(clean_reply)
        # Invented markers like «[forward]» at a line end never reach the chat.
        clean_reply = strip_stray_tags(
            clean_reply, keep=(get_content().llm.block_marker,)
        )
        messages = delivery_messages(ctx, clean_reply)
        clean_reply = marker_free_reply(clean_reply)
        ctx.reply = clean_reply
        photo_file_id, photo_data_url = photo_fields(ctx)

        await self._messages.create(
            role="assistant",
            content=clean_reply,
            channel=turn_channel(ctx.turn),
        )
        session_key = dialogue_session_key(
            channel=turn_channel(ctx.turn),
            telegram_chat_id=ctx.turn.telegram_chat_id,
        )
        self._decision.record_reply(session_key)
        if self._meme_decider is not None:
            self._meme_decider.register_reply(session_key)

        ctx.result = ConversationTurnResult(
            action=ctx.decision.action.value,
            reason=ctx.decision.reason.value,
            reply=clean_reply,
            messages=messages,
            context_count=ctx.context_count,
            relevance_score=ctx.decision.relevance_score,
            sticker_tag=sticker_tag,
            photo_file_id=photo_file_id,
            photo_data_url=photo_data_url,
        )
        self._metrics.record_turn(
            action=ctx.result.action,
            reason=ctx.result.reason,
            planner_skipped=ctx.planner_skipped,
            deep_search=ctx.turn_plan.deep_search,
        )
        return True
