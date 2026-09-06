from vanessa.config.content import get_content
from vanessa.core.protocols import (
    MessageIndexingSchedulerProtocol,
    MessageRepositoryProtocol,
    TurnMetricsProtocol,
)
from vanessa.core.turn import ConversationTurnResult
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.models import DecisionAction
from vanessa.pipeline.decision.protocols import DecisionEngineProtocol
from vanessa.pipeline.gate_support import index_user_on_ignore
from vanessa.pipeline.llm.format.answer_tag import strip_control_tags
from vanessa.pipeline.llm.format.message_blocks import (
    split_reply_into_blocks,
    strip_block_markers,
)
from vanessa.pipeline.llm.format.reply_format import strip_trailing_periods
from vanessa.pipeline.llm.format.sticker_tag import extract_sticker_tag
from vanessa.pipeline.llm.memes import MemeDecider
from vanessa.pipeline.orchestrator.orchestrator_config import OrchestratorConfig


class FinalizeStage:
    def __init__(
        self,
        messages: MessageRepositoryProtocol,
        indexing: MessageIndexingSchedulerProtocol,
        decision_engine: DecisionEngineProtocol,
        config: OrchestratorConfig,
        metrics: TurnMetricsProtocol,
        *,
        meme_decider: MemeDecider | None = None,
    ) -> None:
        self._messages = messages
        self._indexing = indexing
        self._decision = decision_engine
        self._config = config
        self._metrics = metrics
        self._meme_decider = meme_decider

    async def skip(self, ctx: TurnPipelineContext, *, reason: str) -> None:
        """Finish the turn without a reply.

        Used when a later stage decides the user's message does not need a
        reply. The user message is still indexed and the turn is recorded as
        ignored (no assistant message is created, no reply is registered).
        """
        await index_user_on_ignore(ctx, self._indexing, self._config)
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

        if self._config.defer_index_on_ignore:
            self._indexing.schedule(ctx.user_msg)
        else:
            await self._indexing.index_now(ctx.user_msg)

        clean_reply, sticker_tag = extract_sticker_tag(ctx.reply)
        # Final control-tag safety net: a reasoning model may emit [answer] /
        # <answer> / [ignore] in a form the provider's splitter missed — never
        # let a control tag reach the chat. The [next] block marker is left for
        # the block splitter below, which needs it to separate the messages.
        clean_reply = strip_control_tags(clean_reply)
        # Split the reply into the individual Telegram messages to send (on the
        # marker-containing text, so the model's explicit `[next]` blocks drive
        # the split; a deterministic sentence-aware split is the fallback when
        # the model skipped markers). The persona avoids a trailing period at the
        # end of a message, so it is cut deterministically from EVERY delivered
        # block (not just the overall reply); the marker-free full text is what
        # stays in the DB and metrics.
        marker = get_content().llm.block_marker
        messages = [
            block
            for block in (
                strip_trailing_periods(b)
                for b in split_reply_into_blocks(clean_reply, marker=marker)
            )
            if block.strip()
        ]
        clean_reply = strip_block_markers(clean_reply, marker=marker)
        ctx.reply = clean_reply

        await self._messages.create(
            role="assistant",
            content=clean_reply,
        )
        self._decision.record_reply(ctx.turn.telegram_chat_id)
        if self._meme_decider is not None:
            self._meme_decider.register_reply(ctx.turn.telegram_chat_id)

        ctx.result = ConversationTurnResult(
            action=ctx.decision.action.value,
            reason=ctx.decision.reason.value,
            reply=clean_reply,
            messages=messages,
            context_count=ctx.context_count,
            relevance_score=ctx.decision.relevance_score,
            sticker_tag=sticker_tag,
            # Photo the compose model asked to re-send (resolved from [photo:N]).
            photo_file_id=ctx.photo_file_id,
            # Stored bytes of the same photo, so the bot can fall back to an
            # upload when the Telegram file_id is stale at delivery time.
            photo_data_url=ctx.photo_data_url,
        )
        self._metrics.record_turn(
            action=ctx.result.action,
            reason=ctx.result.reason,
            planner_skipped=ctx.planner_skipped,
            deep_search=ctx.turn_plan.deep_search,
        )
        return True
