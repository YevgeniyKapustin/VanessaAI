import logging
import time

from app.core.session.chat_session_state import load_chat_session_state
from app.core.users.display_names import resolve_user_display_name
from app.core.protocols import (
    IncomingTurnHandlerProtocol,
    MessageRepositoryProtocol,
    UserRepositoryProtocol,
)
from app.db.repository import MessageRepository
from app.knowledge.memory_stage import MemoryStage
from app.knowledge.metrics.pipeline import MetricsPipeline
from app.core.request_context import get_planning_started_signal, get_request_id
from app.core.turn import ChatTurnInput, ConversationTurnResult
from app.decision.models import DecisionAction, DecisionReason
from app.observability.eval import RagTriadEvaluator
from app.observability.metrics import record_stage, record_turn_duration
from app.observability.tracing import get_tracer, hash_identifier
from app.services.background import BackgroundExecutor
from app.services.orchestrator.orchestrator_config import OrchestratorConfig
from app.services.pipeline.context import TurnPipelineContext
from app.services.pipeline.protocols import FinalizeStageProtocol, PipelineStage

logger = logging.getLogger(__name__)

_PREVIEW_LEN = 80


def _preview(text: str) -> str:
    normalized = text.replace("\n", " ").strip()
    if len(normalized) <= _PREVIEW_LEN:
        return normalized
    return f"{normalized[:_PREVIEW_LEN]}..."


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
        background: BackgroundExecutor | None = None,
        session_factory=None,
        eval: RagTriadEvaluator | None = None,
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
        self._background = background
        self._session_factory = session_factory
        self._eval = eval

    async def handle_incoming(self, turn: ChatTurnInput) -> ConversationTurnResult:
        tracer = get_tracer()
        async with tracer.trace(
            name="telegram_rag_pipeline",
            user_id=hash_identifier(turn.sender_telegram_id),
            session_id=str(turn.telegram_chat_id),
            metadata={
                "request_id": get_request_id(),
                "chat_id": hash_identifier(turn.telegram_chat_id),
                "message_preview": _preview(turn.message),
            },
            input=turn.message,
        ):
            return await self._handle_incoming_inner(turn)

    async def _handle_incoming_inner(self, turn: ChatTurnInput) -> ConversationTurnResult:
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

        if not await self._run_stage("gate", self._gate.run(ctx)):
            self._log_processed(turn, ctx)
            assert ctx.result is not None
            return ctx.result

        # The decision gate has passed and Vanessa is committing to an actual
        # reply: notify the caller (the API chat route streams this to the bot)
        # so the "typing..." indicator starts only now — never for messages
        # that got filtered out. Fail-open: a broken signal must not block the
        # turn.
        signal = get_planning_started_signal()
        if signal is not None:
            try:
                await signal()
            except Exception:
                logger.exception(
                    "planning_started_signal_failed request_id=%s", get_request_id()
                )

        await self._run_stage("retrieve", self._retrieve.run(ctx))
        await self._run_stage("compose", self._compose.run(ctx))
        if self._critique is not None:
            if not await self._run_stage("critique", self._critique.run(ctx)):
                # The critic decided the message does not need a reply.
                await self._finalize.skip(
                    ctx,
                    reason=DecisionReason.NO_REPLY_NEEDED.value,
                )
                self._log_processed(turn, ctx)
                assert ctx.result is not None
                return ctx.result
        await self._run_stage("finalize", self._finalize.run(ctx))
        await self._run_post_reply(ctx)
        self._log_processed(turn, ctx)
        assert ctx.result is not None
        return ctx.result

    async def _run_stage(self, name: str, coro) -> bool:
        """Run a pipeline stage inside a tracing span (no-op when disabled)."""
        tracer = get_tracer()
        async with tracer.span(name=name):
            return await coro

    async def _run_post_reply(self, ctx: TurnPipelineContext) -> None:
        """Run memory extraction + metrics.

        With a background executor injected, both are submitted as jobs and the
        reply returns immediately (non-blocking). Without one (unit tests /
        fallback) they run inline exactly as before.
        """
        if self._background is not None:
            if self._memory is not None:
                self._background.submit(self._build_memory_job(ctx))
            if self._metrics is not None:
                self._background.submit(self._build_metrics_job())
            if self._eval is not None and self._eval.should_run():
                self._background.submit(self._build_eval_job(ctx))
            return
        if self._memory is not None:
            try:
                await self._memory.run(
                    recent_messages=ctx.recent,
                    source_message_ids=[ctx.user_msg.id] if ctx.user_msg else None,
                )
            except Exception:
                logger.exception(
                    "memory_stage_run_failed request_id=%s", get_request_id()
                )
        if self._metrics is not None:
            try:
                await self._metrics.run(self._messages, semantic=False)
            except Exception:
                logger.exception(
                    "metrics_stage_run_failed request_id=%s", get_request_id()
                )

    def _build_memory_job(self, ctx: TurnPipelineContext):
        recent = ctx.recent
        source_ids = [ctx.user_msg.id] if ctx.user_msg is not None else None

        async def job() -> None:
            try:
                assert self._memory is not None
                await self._memory.run(
                    recent_messages=recent,
                    source_message_ids=source_ids,
                )
            except Exception:
                logger.exception(
                    "memory_stage_run_failed request_id=%s", get_request_id()
                )

        return job

    def _build_metrics_job(self):
        async def job() -> None:
            try:
                assert self._metrics is not None
                if self._session_factory is not None:
                    # The request-scoped repo dies with the response, so metrics
                    # must open its own session in the background.
                    async with self._session_factory() as session:
                        await self._metrics.run(
                            MessageRepository(session),
                            semantic=False,
                        )
                else:
                    await self._metrics.run(self._messages, semantic=False)
            except Exception:
                logger.exception(
                    "metrics_stage_run_failed request_id=%s", get_request_id()
                )

        return job

    def _build_eval_job(self, ctx: TurnPipelineContext):
        question = ctx.turn.message
        answer = ctx.reply or ""
        context = self._eval_context_text(ctx)

        async def job() -> None:
            try:
                assert self._eval is not None
                await self._eval.evaluate(
                    question=question,
                    answer=answer,
                    context=context,
                )
            except Exception:
                logger.exception(
                    "rag_eval_failed request_id=%s", get_request_id()
                )

        return job

    @staticmethod
    def _eval_context_text(ctx: TurnPipelineContext) -> str:
        """Flatten the retrieved context into plain text for the judge."""
        parts: list[str] = []
        for block in ctx.knowledge_blocks:
            if block.content.strip():
                parts.append(block.content.strip())
        for block in ctx.context_blocks:
            for message in block.messages:
                if message.content.strip():
                    parts.append(message.content.strip())
        parts.extend(quote.strip() for quote in ctx.humor_quotes if quote.strip())
        return "\n\n".join(parts)

    def _log_processed(self, turn: ChatTurnInput, ctx: TurnPipelineContext) -> None:
        assert ctx.result is not None
        total_ms = (time.perf_counter() - ctx.started) * 1000
        # Export latency histograms to Prometheus (dashboards + AlertManager).
        record_turn_duration(action=ctx.result.action, seconds=total_ms / 1000.0)
        record_stage("total", seconds=total_ms / 1000.0)
        for stage, ms in (
            ("plan", ctx.plan_ms),
            ("decision", ctx.decision_ms),
            ("embed", ctx.embed_ms),
            ("rag", ctx.rag_ms),
            ("humor_rag", ctx.humor_rag_ms),
            ("llm", ctx.llm_ms),
            ("critic", ctx.critic_ms),
        ):
            if ms > 0:
                record_stage(stage, seconds=ms / 1000.0)
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
