from __future__ import annotations

import logging

from vanessa.config.owners import owner_id_for
from vanessa.core.protocols import TurnMetricsProtocol
from vanessa.core.request_context import get_request_id
from vanessa.core.turn import ConversationTurnResult
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.gate.eligibility.ignore_registry_protocol import (
    ChatIgnoreRegistryProtocol,
)
from vanessa.pipeline.decision.gate.eligibility.reply_eligibility import (
    prefilter_tag_to_decision_reason,
)
from vanessa.pipeline.decision.gate.eligibility.user_ignore import (
    apply_owner_ignore_command,
)
from vanessa.pipeline.decision.models import DecisionAction

logger = logging.getLogger(__name__)


async def apply_owner_ignore_if_needed(
    registry: ChatIgnoreRegistryProtocol,
    ctx: TurnPipelineContext,
) -> None:
    owner_id = owner_id_for(ctx.turn.sender_telegram_id)
    if not owner_id:
        return
    apply_owner_ignore_command(
        registry,
        chat_id=ctx.turn.telegram_chat_id,
        owner_id=owner_id,
        sender_id=ctx.turn.sender_telegram_id,
        text=ctx.turn.message,
        recent_messages=ctx.recent,
        reply_to_sender_id=ctx.turn.reply_to_sender_telegram_id,
    )


async def finish_ignore_turn(
    ctx: TurnPipelineContext,
    *,
    reason: str,
    metrics: TurnMetricsProtocol,
    planner_skipped: bool,
    relevance_score: float = 0.0,
    log_event: str,
) -> None:
    logger.info(
        "%s request_id=%s reason=%s action=ignore",
        log_event,
        get_request_id(),
        reason,
    )
    ctx.result = ConversationTurnResult(
        action=DecisionAction.IGNORE.value,
        reason=reason,
        relevance_score=relevance_score,
    )
    metrics.record_turn(
        action=ctx.result.action,
        reason=ctx.result.reason,
        planner_skipped=planner_skipped,
    )


def decision_reason_from_prefilter_tag(tag: str) -> str:
    return prefilter_tag_to_decision_reason(tag).value


async def finish_decision_ignore(
    ctx: TurnPipelineContext,
    *,
    metrics: TurnMetricsProtocol,
) -> None:
    assert ctx.decision is not None
    await finish_ignore_turn(
        ctx,
        reason=ctx.decision.reason.value,
        metrics=metrics,
        planner_skipped=ctx.planner_skipped,
        relevance_score=ctx.decision.relevance_score,
        log_event="turn_stage decision_ignore",
    )
