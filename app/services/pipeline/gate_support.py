from __future__ import annotations

import logging

from app.config.settings import settings
from app.core.protocols import (
    MessageIndexingSchedulerProtocol,
    TurnMetricsProtocol,
)
from app.core.request_context import get_request_id
from app.core.turn import ConversationTurnResult
from app.decision.gate.reply_eligibility import prefilter_tag_to_decision_reason
from app.decision.gate.ignore_registry_protocol import ChatIgnoreRegistryProtocol
from app.decision.gate.user_ignore import (
    apply_owner_ignore_command,
)
from app.decision.models import DecisionAction, DecisionReason
from app.services.orchestrator.orchestrator_config import OrchestratorConfig
from app.services.pipeline.context import TurnPipelineContext

logger = logging.getLogger(__name__)


async def apply_owner_ignore_if_needed(
    registry: ChatIgnoreRegistryProtocol,
    ctx: TurnPipelineContext,
) -> None:
    owner_id = settings.required_user_telegram_id
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
    indexing: MessageIndexingSchedulerProtocol,
    config: OrchestratorConfig,
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
    await index_user_on_ignore(ctx, indexing, config)
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


async def index_user_on_ignore(
    ctx: TurnPipelineContext,
    indexing: MessageIndexingSchedulerProtocol,
    config: OrchestratorConfig,
) -> None:
    assert ctx.user_msg is not None
    if config.defer_index_on_ignore:
        indexing.schedule(ctx.user_msg)
    else:
        await indexing.index_now(ctx.user_msg)


async def finish_decision_ignore(
    ctx: TurnPipelineContext,
    *,
    metrics: TurnMetricsProtocol,
    indexing: MessageIndexingSchedulerProtocol,
    config: OrchestratorConfig,
) -> None:
    assert ctx.decision is not None
    await finish_ignore_turn(
        ctx,
        reason=ctx.decision.reason.value,
        metrics=metrics,
        indexing=indexing,
        config=config,
        planner_skipped=ctx.planner_skipped,
        relevance_score=ctx.decision.relevance_score,
        log_event="turn_stage decision_ignore",
    )
