import logging
import time

from app.core.session.chat_session_state import load_chat_session_state
from app.core.users.display_names import resolve_user_display_name
from app.core.protocols import (
    IncomingTurnHandlerProtocol,
    MessageRepositoryProtocol,
    UserRepositoryProtocol,
)
from app.knowledge.memory_stage import MemoryStage
from app.knowledge.metrics.pipeline import MetricsPipeline
from app.core.request_context import get_request_id
from app.core.turn import ChatTurnInput, ConversationTurnResult
from app.decision.models import DecisionAction, DecisionReason
from app.services.orchestrator.orchestrator_config import OrchestratorConfig
from app.services.pipeline.context import TurnPipelineContext
from app.services.pipeline.protocols import FinalizeStageProtocol, PipelineStage

logger = logging.getLogger(__name__)


class ConversationOrchestrator(IncomingTurnHandlerProtocol):
    def __init__(
        self,
        messages: MessageRepositoryProtocol,
        users: UserRepositoryProtocol,
        config: OrchestratorConfig,
        gate: PipelineStage,
        retrieve: PipelineStage,
        compose: PipelineStage,
        finalize: FinalizeStageProtocol,
        critique: PipelineStage | None = None,
        memory: MemoryStage | None = None,
        metrics: MetricsPipeline | None = None,
    ) -> None:
        self._messages = messages
        self._users = users
        self._config = config
        self._gate = gate
        self._retrieve = retrieve
        self._compose = compose
        self._finalize = finalize
        self._critique = critique
        self._memory = memory
        self._metrics = metrics

    async def handle_incoming(self, turn: ChatTurnInput) -> ConversationTurnResult:
        ctx = TurnPipelineContext(turn=turn)

        user = await self._users.get_or_create(
            telegram_id=turn.sender_telegram_id,
            username=turn.sender_username,
            first_name=turn.sender_first_name,
            last_name=turn.sender_last_name,
        )
        ctx.sender_name = resolve_user_display_name(
            turn.sender_telegram_id,
            nickname=user.nickname,
            first_name=user.first_name or turn.sender_first_name,
            username=user.username or turn.sender_username,
        )

        ctx.user_msg = await self._messages.create(
            role="user",
            content=turn.message,
            sender_telegram_id=turn.sender_telegram_id,
            reply_to_message_id=turn.reply_to_message_id,
            reply_to_text=turn.reply_to_text,
            reply_to_sender_telegram_id=turn.reply_to_sender_telegram_id,
            reply_to_sender_name=turn.reply_to_sender_name,
        )

        ctx.session = await load_chat_session_state(
            self._messages,
            window_size=self._config.session_window_size,
            max_idle_seconds=self._config.session_idle_seconds,
            listen_max_messages=self._config.post_reply_listen_count,
        )
        ctx.recent = ctx.session.recent_messages

        if not await self._gate.run(ctx):
            self._log_processed(turn, ctx)
            assert ctx.result is not None
            return ctx.result

        await self._retrieve.run(ctx)
        await self._compose.run(ctx)
        if self._critique is not None:
            if not await self._critique.run(ctx):
                # The critic decided the message does not need a reply.
                await self._finalize.skip(
                    ctx,
                    reason=DecisionReason.NO_REPLY_NEEDED.value,
                )
                self._log_processed(turn, ctx)
                assert ctx.result is not None
                return ctx.result
        await self._finalize.run(ctx)
        if self._memory is not None:
            try:
                await self._memory.run(
                    recent_messages=ctx.recent,
                    source_message_ids=[ctx.user_msg.id] if ctx.user_msg else None,
                )
            except Exception:
                logger.exception("memory_stage_run_failed request_id=%s", get_request_id())
        if self._metrics is not None:
            try:
                await self._metrics.run(self._messages, semantic=False)
            except Exception:
                logger.exception("metrics_stage_run_failed request_id=%s", get_request_id())
        self._log_processed(turn, ctx)
        assert ctx.result is not None
        return ctx.result

    def _log_processed(self, turn: ChatTurnInput, ctx: TurnPipelineContext) -> None:
        assert ctx.result is not None
        total_ms = (time.perf_counter() - ctx.started) * 1000
        if ctx.result.action == DecisionAction.IGNORE.value:
            logger.info(
                "turn_processed request_id=%s chat_id=%s sender_id=%s action=%s "
                "reason=%s relevance=%.3f planner_skipped=%s plan_ms=%.1f "
                "decision_ms=%.1f total_ms=%.1f",
                get_request_id(),
                turn.telegram_chat_id,
                turn.sender_telegram_id,
                ctx.result.action,
                ctx.result.reason,
                ctx.result.relevance_score,
                ctx.planner_skipped,
                ctx.plan_ms,
                ctx.decision_ms,
                total_ms,
            )
            return

        turn_plan = ctx.turn_plan
        critic_verdict = ctx.critic_verdict
        critic_status = critic_verdict.status.value if critic_verdict else "-"
        critic_score = critic_verdict.score if critic_verdict else 0
        logger.info(
            "turn_processed request_id=%s chat_id=%s sender_id=%s action=%s "
            "reason=%s relevance=%.3f search=%r skip=%s humor_quotes=%s "
            "context=%s critic_status=%s critic_score=%s critic_iterations=%s "
            "sticker_tag=%s "
            "plan_ms=%.1f embed_ms=%.1f decision_ms=%.1f rag_ms=%.1f "
            "humor_rag_ms=%.1f llm_ms=%.1f critic_ms=%.1f total_ms=%.1f",
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
            critic_status,
            critic_score,
            ctx.critic_iterations,
            ctx.result.sticker_tag,
            ctx.plan_ms,
            ctx.embed_ms,
            ctx.decision_ms,
            ctx.rag_ms,
            ctx.humor_rag_ms,
            ctx.llm_ms,
            ctx.critic_ms,
            total_ms,
        )
