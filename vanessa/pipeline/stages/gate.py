import logging
import time

from vanessa.config.settings import settings
from vanessa.core.protocols import (
    MessageRepositoryProtocol,
    TurnMetricsProtocol,
)
from vanessa.core.request_context import get_request_id
from vanessa.knowledge.metrics.retriever import MetricsRetriever
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.bot_peer_budget import BotPeerBudget
from vanessa.pipeline.decision.gate.eligibility.ignore_registry_protocol import (
    ChatIgnoreRegistryProtocol,
)
from vanessa.pipeline.decision.gate.protocols import (
    PlannerPrefilterProtocol,
    ReactionGateProtocol,
    TurnPlannerProtocol,
)
from vanessa.pipeline.decision.models import DecisionAction
from vanessa.pipeline.decision.protocols import DecisionEngineProtocol
from vanessa.pipeline.decision.repeated_loop import LoopRegistry
from vanessa.pipeline.decision.repeated_loop import (
    loop_registry as default_loop_registry,
)
from vanessa.pipeline.gate_support import (
    apply_owner_ignore_if_needed,
    finish_decision_ignore,
)
from vanessa.pipeline.orchestrator.orchestrator_config import OrchestratorConfig
from vanessa.pipeline.stages.bot_peer import _GateBotPeerMixin
from vanessa.pipeline.stages.gate_decision import (
    decision_context_from_pipeline,
    pipeline_in_listen_window,
)
from vanessa.pipeline.stages.gate_filters import _GateFilterMixin
from vanessa.pipeline.stages.gate_vision import _GateVisionMixin

logger = logging.getLogger("vanessa.pipeline.stages")


class GateStage(_GateVisionMixin, _GateFilterMixin, _GateBotPeerMixin):
    def __init__(
        self,
        query_rewriter: TurnPlannerProtocol,
        decision_engine: DecisionEngineProtocol,
        planner_prefilter: PlannerPrefilterProtocol | None,
        config: OrchestratorConfig,
        metrics: TurnMetricsProtocol,
        messages: MessageRepositoryProtocol,
        ignore_registry: ChatIgnoreRegistryProtocol,
        metrics_retriever: MetricsRetriever | None = None,
        reaction_gate: ReactionGateProtocol | None = None,
        loop_registry: LoopRegistry | None = None,
        bot_budget: BotPeerBudget | None = None,
    ) -> None:
        self._planner = query_rewriter
        self._decision = decision_engine
        self._prefilter = planner_prefilter
        self._loop_registry = loop_registry or default_loop_registry
        # Lightweight pre-planner classifier: when it says the message does not
        # need a reaction, the turn is finalized immediately and the expensive
        # LLM planner is never invoked.
        self._reaction_gate = reaction_gate
        self._config = config
        self._metrics = metrics
        self._messages = messages
        self._ignore_registry = ignore_registry
        self._metrics_retriever = metrics_retriever
        self._bot_budget = bot_budget or BotPeerBudget()

    async def run(self, ctx: TurnPipelineContext) -> bool:
        await apply_owner_ignore_if_needed(self._ignore_registry, ctx)
        if await self._bot_peer_should_stop(ctx):
            return False
        photo_done = await self._gate_bare_photo(ctx)
        if photo_done is not None:
            return photo_done
        if await self._filters_should_stop(ctx):
            return False
        return await self._plan_decide_and_finish(ctx)

    async def _plan_decide_and_finish(self, ctx: TurnPipelineContext) -> bool:
        rewrite_started = time.perf_counter()
        assert ctx.session is not None
        ctx.turn_plan = await self._planner.prepare(
            ctx.turn.message,
            recent_messages=ctx.recent,
            mentions_bot=ctx.turn.mentions_bot,
            reply_to_bot=ctx.turn.reply_to_bot,
            reply_to_other_user=ctx.turn.reply_to_other_user,
            in_listen_window=pipeline_in_listen_window(ctx),
            sender_name=ctx.sender_name,
        )
        ctx.plan_ms = (time.perf_counter() - rewrite_started) * 1000
        await self._load_sender_profile(ctx)
        self._apply_loop_signal(ctx)

        decision_started = time.perf_counter()
        ctx.decision = await self._decision.decide(
            decision_context_from_pipeline(ctx),
            humor_ok=ctx.turn_plan.humor_ok,
        )
        ctx.decision_ms = (time.perf_counter() - decision_started) * 1000
        self._log_gate_plan(ctx)

        if ctx.decision.action == DecisionAction.IGNORE:
            await finish_decision_ignore(
                ctx,
                metrics=self._metrics,
            )
            return False
        return True

    def _apply_loop_signal(self, ctx: TurnPipelineContext) -> None:
        # Same sender, same ask at least twice already — not a follow-up.
        if ctx.turn_plan is None:
            return
        signal = self._loop_registry.update(
            ctx.turn.sender_telegram_id,
            ctx.turn.message,
            ctx.recent,
            planner_repeated=ctx.turn_plan.repeated_topic,
            planner_loop_level=ctx.turn_plan.loop_level,
            window=settings.decision_loop_window,
            similarity_threshold=settings.decision_loop_similarity_threshold,
            decay_half_life_seconds=settings.decision_loop_decay_half_life_seconds,
        )
        ctx.loop_strength = signal.loop_strength
        ctx.annoyance = signal.annoyance

    def _log_gate_plan(self, ctx: TurnPipelineContext) -> None:
        logger.info(
            "turn_stage plan request_id=%s search=%r skip=%s should_reply=%s "
            "humor_ok=%s humor_query=%r deep_search=%s listen_window=%s "
            "needs_clarification=%s detail=%s reaction_gate_ms=%.1f plan_ms=%.1f "
            "decision_ms=%.1f action=%s reason=%s",
            get_request_id(),
            ctx.turn_plan.text,
            ctx.turn_plan.skip_search,
            ctx.turn_plan.should_reply,
            ctx.turn_plan.humor_ok,
            ctx.turn_plan.humor_query,
            ctx.turn_plan.deep_search,
            pipeline_in_listen_window(ctx),
            ctx.turn_plan.needs_clarification,
            ctx.turn_plan.detail,
            ctx.reaction_gate_ms,
            ctx.plan_ms,
            ctx.decision_ms,
            ctx.decision.action.value,
            ctx.decision.reason.value,
        )
