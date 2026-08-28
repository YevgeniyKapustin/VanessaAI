import logging
import time

from app.config.settings import settings
from app.core.messages import ImageAttachment, attachments_to_dicts
from app.core.session.chat_session_state import load_chat_session_state
from app.core.users.display_names import resolve_user_display_name
from app.core.protocols import (
    IncomingTurnHandlerProtocol,
    MessageRepositoryProtocol,
    PhotoCaptionerProtocol,
    UserRepositoryProtocol,
)
from app.db.repository import MessageRepository
from app.knowledge.memory_stage import MemoryStage
from app.knowledge.metrics.pipeline import MetricsPipeline
from app.core.request_context import get_planning_started_signal, get_request_id
from app.core.turn import ChatTurnInput, ConversationTurnResult
from app.decision.models import DecisionAction
from app.observability.eval import RagTriadEvaluator
from app.observability.metrics import (
    record_reply_length,
    record_stage,
    record_turn_duration,
    record_user_activity,
)
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
        memory: MemoryStage | None = None,
        metrics: MetricsPipeline | None = None,
        background: BackgroundExecutor | None = None,
        session_factory=None,
        eval: RagTriadEvaluator | None = None,
        photo_captioner: PhotoCaptionerProtocol | None = None,
    ) -> None:
        self._messages = messages
        self._users = users
        self._config = config
        self._gate = gate
        self._retrieve = retrieve
        self._compose = compose
        self._finalize = finalize
        self._memory = memory
        self._metrics = metrics
        self._background = background
        self._session_factory = session_factory
        self._eval = eval
        self._photo_captioner = photo_captioner

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
        # Track the sender and chat for the active-user / concurrent-dialog
        # gauges (DAU, sessions) — every processed message counts as activity.
        record_user_activity(turn.sender_telegram_id, turn.telegram_chat_id)

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
            # Persist vision images so a follow-up turn ("а переведи вон ту
            # надпись на ней") can reload them from the session window.
            attachments=attachments_to_dicts(turn.images) or None,
        )

        ctx.session = await load_chat_session_state(
            self._messages,
            window_size=self._config.session_window_size,
            max_idle_seconds=self._config.session_idle_seconds,
            listen_max_messages=self._config.post_reply_listen_count,
        )
        ctx.recent = ctx.session.recent_messages

        if not await self._run_stage(
            "gate",
            self._gate.run(ctx),
            output=lambda: ctx.turn_plan.to_trace_dict()
            if ctx.turn_plan is not None
            else None,
        ):
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

        # The compose stage refused the answer (repeated same-sender message /
        # spam, or the compose model returned an empty "stay silent" reply):
        # finalize the turn as an IGNORE instead of sending a reply. The user
        # message is still indexed, no assistant message is created, nothing is
        # delivered to the chat, and post-reply memory/metrics are skipped — the
        # same shape as a gate-level ignore.
        if ctx.refuse_reason is not None:
            await self._finalize.skip(ctx, reason=ctx.refuse_reason)
            self._log_processed(turn, ctx)
            assert ctx.result is not None
            return ctx.result

        await self._run_stage("finalize", self._finalize.run(ctx))
        await self._run_post_reply(ctx)
        self._log_processed(turn, ctx)
        assert ctx.result is not None
        return ctx.result

    async def _run_stage(self, name: str, coro, *, output=None) -> bool:
        """Run a pipeline stage inside a tracing span (no-op when disabled).

        ``output`` is an optional zero-arg callable evaluated after the stage
        completes, while the span is still open, so a stage can attach its
        result to the trace — the gate attaches the parsed ``TurnPlan`` so the
        planner's output is visible in Langfuse for debugging.
        """
        tracer = get_tracer()
        async with tracer.span(name=name) as span:
            ok = await coro
            if output is not None:
                span.update(output=output())
            return ok

    async def _run_post_reply(self, ctx: TurnPipelineContext) -> None:
        """Run memory extraction + metrics + photo captioning.

        With a background executor injected, all are submitted as jobs and the
        reply returns immediately (non-blocking). Without one (unit tests /
        fallback) they run inline exactly as before.
        """
        caption_job = self._build_photo_caption_job(ctx)
        if self._background is not None:
            if self._memory is not None:
                self._background.submit(self._build_memory_job(ctx))
            if self._metrics is not None:
                self._background.submit(self._build_metrics_job(ctx))
            if self._eval is not None and self._eval.should_run():
                self._background.submit(self._build_eval_job(ctx))
            if caption_job is not None:
                self._background.submit(caption_job)
            return
        if caption_job is not None:
            await caption_job()
        if self._memory is not None:
            try:
                await self._memory.run(
                    recent_messages=ctx.recent,
                    source_message_ids=[ctx.user_msg.id] if ctx.user_msg else None,
                    telegram_chat_id=ctx.turn.telegram_chat_id,
                )
            except Exception:
                logger.exception(
                    "memory_stage_run_failed request_id=%s", get_request_id()
                )
        if self._metrics is not None:
            try:
                await self._metrics.run(
                    self._messages,
                    semantic=False,
                    only_senders={ctx.turn.sender_telegram_id},
                )
            except Exception:
                logger.exception(
                    "metrics_stage_run_failed request_id=%s", get_request_id()
                )

    def _build_memory_job(self, ctx: TurnPipelineContext):
        recent = ctx.recent
        source_ids = [ctx.user_msg.id] if ctx.user_msg is not None else None
        chat_id = ctx.turn.telegram_chat_id

        async def job() -> None:
            try:
                assert self._memory is not None
                await self._memory.run(
                    recent_messages=recent,
                    source_message_ids=source_ids,
                    telegram_chat_id=chat_id,
                )
            except Exception:
                logger.exception(
                    "memory_stage_run_failed request_id=%s", get_request_id()
                )

        return job

    def _build_metrics_job(self, ctx: TurnPipelineContext):
        sender_id = ctx.turn.sender_telegram_id

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
                            only_senders={sender_id},
                        )
                else:
                    await self._metrics.run(
                        self._messages,
                        semantic=False,
                        only_senders={sender_id},
                    )
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

    def _build_photo_caption_job(self, ctx: TurnPipelineContext):
        """Enrich a photo message with a short generated caption (background).

        The caption is stored in ``messages.photo_caption`` and folded into the
        FTS search_vector, so a bare photo becomes findable "by meaning" in RAG
        and is listed (with its caption) in the photo album the compose model
        can pick from. Returns None when there is nothing to caption.
        """
        if (
            self._photo_captioner is None
            or not settings.vision_photo_caption_enabled
        ):
            return None
        user_msg = ctx.user_msg
        if user_msg is None or not user_msg.attachments:
            return None
        first_attachment = user_msg.attachments[0]
        if not isinstance(first_attachment, dict):
            return None
        attachment = ImageAttachment.from_dict(first_attachment)
        if not attachment.data_url:
            return None
        message_id = user_msg.id

        async def job() -> None:
            try:
                caption = await self._photo_captioner.generate(attachment)
                if not caption:
                    return
                if self._session_factory is not None:
                    # The request-scoped repo dies with the response, so the job
                    # opens its own session in the background.
                    async with self._session_factory() as session:
                        await MessageRepository(session).update_photo_caption(
                            message_id, caption
                        )
                else:
                    await self._messages.update_photo_caption(message_id, caption)
                logger.info(
                    "photo_caption_stored message_id=%s caption=%r",
                    message_id,
                    caption,
                )
            except Exception:
                logger.exception(
                    "photo_caption_stage_failed request_id=%s", get_request_id()
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
            ("reaction_gate", ctx.reaction_gate_ms),
            ("plan", ctx.plan_ms),
            ("decision", ctx.decision_ms),
            ("embed", ctx.embed_ms),
            ("rag", ctx.rag_ms),
            ("humor_rag", ctx.humor_rag_ms),
            ("llm", ctx.llm_ms),
        ):
            if ms > 0:
                record_stage(stage, seconds=ms / 1000.0)
        if ctx.result.action == DecisionAction.REPLY.value and ctx.reply:
            record_reply_length(action=ctx.result.action, chars=len(ctx.reply))
        if ctx.result.action == DecisionAction.IGNORE.value:
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
            return

        turn_plan = ctx.turn_plan
        logger.info(
            "turn_processed request_id=%s chat_id=%s sender_id=%s action=%s "
            "reason=%s relevance=%.3f search=%r skip=%s humor_quotes=%s "
            "context=%s sticker_tag=%s "
            "reaction_gate_ms=%.1f plan_ms=%.1f embed_ms=%.1f decision_ms=%.1f "
            "rag_ms=%.1f humor_rag_ms=%.1f llm_ms=%.1f total_ms=%.1f",
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
            ctx.embed_ms,
            ctx.decision_ms,
            ctx.rag_ms,
            ctx.humor_rag_ms,
            ctx.llm_ms,
            total_ms,
        )
