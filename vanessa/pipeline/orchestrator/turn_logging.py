import logging
import time

from vanessa.core.request_context import get_request_id
from vanessa.core.turn import ChatTurnInput
from vanessa.infrastructure.observability.metrics import (
    record_reply_length,
    record_stage,
    record_turn_duration,
)
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.models import DecisionAction

logger = logging.getLogger(
    "vanessa.pipeline.orchestrator.conversation_orchestrator"
)

_PREVIEW_LEN = 80


def _preview(text: str) -> str:
    normalized = text.replace("\n", " ").strip()
    if len(normalized) <= _PREVIEW_LEN:
        return normalized
    return f"{normalized[:_PREVIEW_LEN]}..."


def _record_stage_timings(ctx: TurnPipelineContext) -> None:
    for stage, ms in (
        ("reaction_gate", ctx.reaction_gate_ms),
        ("plan", ctx.plan_ms),
        ("decision", ctx.decision_ms),
        ("llm", ctx.llm_ms),
    ):
        if ms > 0:
            record_stage(stage, seconds=ms / 1000.0)


def _log_ignore_turn(
    turn: ChatTurnInput, ctx: TurnPipelineContext, total_ms: float
) -> None:
    assert ctx.result is not None
    logger.info(
        "turn_processed request_id=%s chat_id=%s sender_id=%s action=%s "
        "reason=%s relevance=%.3f planner_skipped=%s reaction_gate_ms=%.1f "
        "plan_ms=%.1f decision_ms=%.1f total_ms=%.1f",
        get_request_id(),
        turn.telegram_chat_id,
        turn.sender_telegram_id,
        ctx.result.action,
        ctx.result.reason,
        ctx.result.relevance_score,
        ctx.planner_skipped,
        ctx.reaction_gate_ms,
        ctx.plan_ms,
        ctx.decision_ms,
        total_ms,
    )


def _log_action_turn(
    turn: ChatTurnInput, ctx: TurnPipelineContext, total_ms: float
) -> None:
    assert ctx.result is not None
    turn_plan = ctx.turn_plan
    logger.info(
        "turn_processed request_id=%s chat_id=%s sender_id=%s action=%s "
        "reason=%s relevance=%.3f search=%r skip=%s humor_quotes=%s "
        "context=%s sticker_tag=%s "
        "reaction_gate_ms=%.1f plan_ms=%.1f decision_ms=%.1f "
        "web_ms=%.1f llm_ms=%.1f total_ms=%.1f",
        get_request_id(),
        turn.telegram_chat_id,
        turn.sender_telegram_id,
        ctx.result.action,
        ctx.result.reason,
        ctx.result.relevance_score,
        turn_plan.text if turn_plan else "",
        turn_plan.skip_search if turn_plan else True,
        len(ctx.humor_quotes),
        ctx.result.context_count,
        ctx.result.sticker_tag,
        ctx.reaction_gate_ms,
        ctx.plan_ms,
        ctx.decision_ms,
        ctx.web_ms,
        ctx.llm_ms,
        total_ms,
    )


class _TurnLoggingMixin:
    def _log_processed(self, turn: ChatTurnInput, ctx: TurnPipelineContext) -> None:
        assert ctx.result is not None
        total_ms = (time.perf_counter() - ctx.started) * 1000
        # Export latency histograms to Prometheus (dashboards + AlertManager).
        record_turn_duration(action=ctx.result.action, seconds=total_ms / 1000.0)
        record_stage("total", seconds=total_ms / 1000.0)
        _record_stage_timings(ctx)
        if ctx.result.action == DecisionAction.REPLY.value and ctx.reply:
            record_reply_length(action=ctx.result.action, chars=len(ctx.reply))
        if ctx.result.action == DecisionAction.IGNORE.value:
            _log_ignore_turn(turn, ctx, total_ms)
            return
        _log_action_turn(turn, ctx, total_ms)
