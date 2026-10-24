import logging
import time

from vanessa.core.request_context import get_request_id
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.models import DecisionReason
from vanessa.pipeline.gate_support import (
    decision_reason_from_prefilter_tag,
    finish_ignore_turn,
)
from vanessa.pipeline.stages.gate_decision import pipeline_in_listen_window

logger = logging.getLogger("vanessa.pipeline.stages")


class _GateFilterMixin:
    async def _filters_should_stop(self, ctx: TurnPipelineContext) -> bool:
        if await self._prefilter_should_stop(ctx):
            return True
        return await self._reaction_gate_should_stop(ctx)

    async def _prefilter_should_stop(self, ctx: TurnPipelineContext) -> bool:
        if not self._config.planner_prefilter_enabled or self._prefilter is None:
            return False
        prefilter = self._prefilter.evaluate(
            ctx.turn.message,
            ctx.recent,
            telegram_chat_id=ctx.turn.telegram_chat_id or 0,
            sender_telegram_id=ctx.turn.sender_telegram_id or 0,
            mentions_bot=ctx.turn.mentions_bot,
            reply_to_bot=ctx.turn.reply_to_bot,
            reply_to_other_user=ctx.turn.reply_to_other_user,
            addressing=ctx.profile.addressing,
            force_listen_window=ctx.profile.listen_window == "on",
        )
        if prefilter.run_planner:
            return False
        ctx.planner_skipped = True
        await finish_ignore_turn(
            ctx,
            reason=decision_reason_from_prefilter_tag(prefilter.reason),
            metrics=self._metrics,
            planner_skipped=True,
            log_event="turn_stage prefilter",
        )
        return True

    async def _reaction_gate_should_stop(self, ctx: TurnPipelineContext) -> bool:
        # Lightweight Decision Gate (reaction classifier): one fast, cheap
        # YES/NO call right before the expensive LLM turn planner. When the
        # answer is NO (people chatting among themselves, the bot's name
        # mentioned in passing, small talk), the turn is finalized instantly
        # and the planner/RAG/compose chain is never invoked.
        if self._reaction_gate is None:
            return False
        assert ctx.session is not None
        gate_started = time.perf_counter()
        reaction = await self._reaction_gate.evaluate(
            ctx.turn.message,
            ctx.recent,
            mentions_bot=ctx.turn.mentions_bot,
            reply_to_bot=ctx.turn.reply_to_bot,
            reply_to_other_user=ctx.turn.reply_to_other_user,
            in_listen_window=pipeline_in_listen_window(ctx),
            sender_telegram_id=ctx.turn.sender_telegram_id,
        )
        ctx.reaction_gate_ms = (time.perf_counter() - gate_started) * 1000
        logger.info(
            "turn_stage reaction_gate request_id=%s respond=%s reason=%s "
            "reaction_gate_ms=%.1f",
            get_request_id(),
            reaction.respond,
            reaction.reason,
            ctx.reaction_gate_ms,
        )
        if reaction.respond:
            return False
        ctx.planner_skipped = True
        await finish_ignore_turn(
            ctx,
            reason=DecisionReason.REACTION_GATE.value,
            metrics=self._metrics,
            planner_skipped=True,
            log_event="turn_stage reaction_gate",
        )
        return True
