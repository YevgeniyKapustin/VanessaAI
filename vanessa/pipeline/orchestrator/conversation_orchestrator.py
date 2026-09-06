from vanessa.core.protocols import (
    IncomingTurnHandlerProtocol,
    MessageRepositoryProtocol,
    PhotoCaptionerProtocol,
    UserRepositoryProtocol,
)
from vanessa.core.request_context import get_request_id
from vanessa.core.turn import ChatTurnInput, ConversationTurnResult
from vanessa.infrastructure.broker.dispatcher import TaskDispatcher
from vanessa.infrastructure.observability.eval import RagTriadEvaluator
from vanessa.infrastructure.observability.tracing import get_tracer, hash_identifier
from vanessa.knowledge.memory import MemoryStage
from vanessa.knowledge.metrics.pipeline import MetricsPipeline
from vanessa.pipeline.background import BackgroundExecutor
from vanessa.pipeline.orchestrator.orchestrator_config import OrchestratorConfig
from vanessa.pipeline.orchestrator.post_reply import _PostReplyMixin
from vanessa.pipeline.orchestrator.turn_ingress import _TurnIngressMixin
from vanessa.pipeline.orchestrator.turn_logging import _preview, _TurnLoggingMixin
from vanessa.pipeline.protocols import FinalizeStageProtocol, PipelineStage


class ConversationOrchestrator(
    _TurnIngressMixin,
    _PostReplyMixin,
    _TurnLoggingMixin,
    IncomingTurnHandlerProtocol,
):
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
        eval: RagTriadEvaluator | None = None,  # noqa: A002 — public constructor kwarg
        photo_captioner: PhotoCaptionerProtocol | None = None,
        dispatcher: TaskDispatcher | None = None,
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
        self._dispatcher = dispatcher

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
        ctx = await self._prepare_incoming_context(turn)

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
        await self._notify_planning_started()
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
