import logging
import time

from app.core.protocols import (
    ContextRetrieverProtocol,
    LLMProviderProtocol,
    MessageIndexingSchedulerProtocol,
    MessageRepositoryProtocol,
    TurnMetricsProtocol,
    UnitOfWorkProtocol,
)
from app.core.request_context import get_request_id
from app.core.turn import ConversationTurnResult
from app.decision.models import DecisionAction, DecisionReason
from app.decision.gate.prefilter import PlannerPrefilter
from app.decision.protocols import DecisionEngineProtocol
from app.llm.prompts.session_format import session_context_messages
from app.rag.query_rewriter import QueryRewriter
from app.rag.search.react_retriever import retrieve_with_react
from app.rag.search.search_plan import build_main_rag_plan
from app.services.humor_pipeline import HumorPipelineProtocol
from app.services.orchestrator.orchestrator_config import OrchestratorConfig
from app.services.pipeline.context import TurnPipelineContext
logger = logging.getLogger(__name__)


class GateStage:
    def __init__(
        self,
        query_rewriter: QueryRewriter,
        decision_engine: DecisionEngineProtocol,
        planner_prefilter: PlannerPrefilter | None,
        config: OrchestratorConfig,
        metrics: TurnMetricsProtocol,
        messages: MessageRepositoryProtocol,
        indexing: MessageIndexingSchedulerProtocol,
    ) -> None:
        self._planner = query_rewriter
        self._decision = decision_engine
        self._prefilter = planner_prefilter
        self._config = config
        self._metrics = metrics
        self._messages = messages
        self._indexing = indexing

    async def run(self, ctx: TurnPipelineContext) -> bool:
        if (
            self._config.planner_prefilter_enabled
            and self._prefilter is not None
        ):
            prefilter = self._prefilter.evaluate(
                ctx.turn.message,
                ctx.recent,
                mentions_bot=ctx.turn.mentions_bot,
                reply_to_bot=ctx.turn.reply_to_bot,
            )
            if not prefilter.run_planner:
                ctx.planner_skipped = True
                logger.info(
                    "turn_stage prefilter request_id=%s reason=%s action=ignore",
                    get_request_id(),
                    prefilter.reason,
                )
                await self._index_user_message(ctx)
                reason = (
                    DecisionReason.DISMISSAL.value
                    if prefilter.reason == "dismissal"
                    else DecisionReason.PREFILTER.value
                )
                ctx.result = ConversationTurnResult(
                    action=DecisionAction.IGNORE.value,
                    reason=reason,
                )
                self._metrics.record_turn(
                    action=ctx.result.action,
                    reason=ctx.result.reason,
                    planner_skipped=True,
                )
                return False

        rewrite_started = time.perf_counter()
        assert ctx.session is not None
        ctx.turn_plan = await self._planner.prepare(
            ctx.turn.message,
            recent_messages=ctx.recent,
            mentions_bot=ctx.turn.mentions_bot,
            reply_to_bot=ctx.turn.reply_to_bot,
            in_listen_window=ctx.session.in_listen_window,
        )
        ctx.plan_ms = (time.perf_counter() - rewrite_started) * 1000

        decision_started = time.perf_counter()
        ctx.decision = await self._decision.decide(
            text=ctx.turn.message,
            telegram_chat_id=ctx.turn.telegram_chat_id,
            recent_messages=ctx.recent,
            search_text=ctx.turn_plan.text if not ctx.turn_plan.skip_search else "",
            should_reply=ctx.turn_plan.should_reply,
            mentions_bot=ctx.turn.mentions_bot,
            reply_to_bot=ctx.turn.reply_to_bot,
            in_listen_window=ctx.session.in_listen_window,
        )
        ctx.decision_ms = (time.perf_counter() - decision_started) * 1000

        logger.info(
            "turn_stage plan request_id=%s search=%r skip=%s should_reply=%s "
            "humor_ok=%s humor_query=%r deep_search=%s listen_window=%s "
            "plan_ms=%.1f decision_ms=%.1f action=%s reason=%s",
            get_request_id(),
            ctx.turn_plan.text,
            ctx.turn_plan.skip_search,
            ctx.turn_plan.should_reply,
            ctx.turn_plan.humor_ok,
            ctx.turn_plan.humor_query,
            ctx.turn_plan.deep_search,
            ctx.session.in_listen_window,
            ctx.plan_ms,
            ctx.decision_ms,
            ctx.decision.action.value,
            ctx.decision.reason.value,
        )

        if ctx.decision.action == DecisionAction.IGNORE:
            await self._index_user_message(ctx)
            ctx.result = ConversationTurnResult(
                action=ctx.decision.action.value,
                reason=ctx.decision.reason.value,
                relevance_score=ctx.decision.relevance_score,
            )
            self._metrics.record_turn(
                action=ctx.result.action,
                reason=ctx.result.reason,
                planner_skipped=ctx.planner_skipped,
            )
            return False
        return True

    async def _index_user_message(self, ctx: TurnPipelineContext) -> None:
        assert ctx.user_msg is not None
        if self._config.defer_index_on_ignore:
            self._indexing.schedule(ctx.user_msg)
        else:
            await self._indexing.index_now(ctx.user_msg)


class RetrieveStage:
    def __init__(
        self,
        retriever: ContextRetrieverProtocol,
        humor_pipeline: HumorPipelineProtocol,
        uow: UnitOfWorkProtocol | None,
    ) -> None:
        self._retriever = retriever
        self._humor = humor_pipeline
        self._uow = uow

    async def run(self, ctx: TurnPipelineContext) -> bool:
        if self._uow is not None:
            await self._uow.commit()

        assert ctx.turn_plan is not None
        if not ctx.turn_plan.skip_search and build_main_rag_plan(
            ctx.turn.message,
            ctx.turn_plan,
        ).semantic_queries:
            embed_started = time.perf_counter()
            ctx.embed_ms = (time.perf_counter() - embed_started) * 1000

        rag_started = time.perf_counter()
        ctx.context_blocks = await retrieve_with_react(
            self._retriever,
            ctx.turn.message,
            ctx.turn_plan,
        )
        ctx.rag_ms = (time.perf_counter() - rag_started) * 1000

        humor_started = time.perf_counter()
        ctx.humor_quotes = await self._humor.fetch_quotes(
            ctx.turn_plan,
            ctx.turn.message,
        )
        ctx.humor_rag_ms = (time.perf_counter() - humor_started) * 1000

        if ctx.humor_quotes:
            logger.info(
                "turn_stage humor_rag request_id=%s humor_query=%r quotes=%s "
                "humor_rag_ms=%.1f",
                get_request_id(),
                ctx.turn_plan.humor_query,
                len(ctx.humor_quotes),
                ctx.humor_rag_ms,
            )

        logger.info(
            "turn_stage rag request_id=%s context=%s deep_search=%s rag_ms=%.1f",
            get_request_id(),
            ctx.context_count,
            ctx.turn_plan.deep_search,
            ctx.rag_ms,
        )
        return True


class ComposeStage:
    def __init__(self, llm: LLMProviderProtocol) -> None:
        self._llm = llm

    async def run(self, ctx: TurnPipelineContext) -> bool:
        llm_started = time.perf_counter()
        session_messages = session_context_messages(ctx.recent)
        ctx.reply = await self._llm.generate(
            user_message=ctx.turn.message,
            context_blocks=ctx.context_blocks,
            session_messages=session_messages,
            humor_quotes=ctx.humor_quotes or None,
            sender_telegram_id=ctx.turn.sender_telegram_id,
            sender_name=ctx.sender_name,
        )
        ctx.llm_ms = (time.perf_counter() - llm_started) * 1000
        logger.info(
            "turn_stage llm request_id=%s reply_len=%s llm_ms=%.1f",
            get_request_id(),
            len(ctx.reply),
            ctx.llm_ms,
        )
        return True


class FinalizeStage:
    def __init__(
        self,
        messages: MessageRepositoryProtocol,
        indexing: MessageIndexingSchedulerProtocol,
        decision_engine: DecisionEngineProtocol,
        config: OrchestratorConfig,
        metrics: TurnMetricsProtocol,
    ) -> None:
        self._messages = messages
        self._indexing = indexing
        self._decision = decision_engine
        self._config = config
        self._metrics = metrics

    async def run(self, ctx: TurnPipelineContext) -> bool:
        assert ctx.user_msg is not None
        assert ctx.decision is not None
        assert ctx.turn_plan is not None
        assert ctx.reply is not None

        if self._config.defer_index_on_ignore:
            self._indexing.schedule(ctx.user_msg)
        else:
            await self._indexing.index_now(ctx.user_msg)

        await self._messages.create(
            role="assistant",
            content=ctx.reply,
        )
        self._decision.record_reply(ctx.turn.telegram_chat_id)

        ctx.result = ConversationTurnResult(
            action=ctx.decision.action.value,
            reason=ctx.decision.reason.value,
            reply=ctx.reply,
            context_count=ctx.context_count,
            relevance_score=ctx.decision.relevance_score,
        )
        self._metrics.record_turn(
            action=ctx.result.action,
            reason=ctx.result.reason,
            planner_skipped=ctx.planner_skipped,
            deep_search=ctx.turn_plan.deep_search,
        )
        return True
