import logging
import time

from app.config import settings
from app.core.display_names import resolve_user_display_name
from app.core.messages import context_block_message_count, stored_to_context
from app.db.repository import UserRepository
from app.llm.humor_quotes import extract_humor_quotes
from app.llm.session_format import session_context_messages
from app.rag.search_plan import build_main_rag_plan
from app.core.protocols import (
    ContextRetrieverProtocol,
    IncomingTurnHandlerProtocol,
    LLMProviderProtocol,
    MessageIndexingSchedulerProtocol,
    MessageRepositoryProtocol,
    TurnQueryProtocol,
    UnitOfWorkProtocol,
)
from app.core.request_context import get_request_id
from app.core.turn import ChatTurnInput, ConversationTurnResult
from app.decision.models import DecisionAction, DecisionReason
from app.decision.prefilter import PlannerPrefilter, in_post_reply_listen_window
from app.decision.protocols import DecisionEngineProtocol
from app.rag.query_rewriter import QueryRewriter

logger = logging.getLogger(__name__)


class ConversationOrchestrator(IncomingTurnHandlerProtocol):
    def __init__(
        self,
        messages: MessageRepositoryProtocol,
        users: UserRepository,
        turn_query: TurnQueryProtocol,
        context_retriever: ContextRetrieverProtocol,
        indexing: MessageIndexingSchedulerProtocol,
        llm: LLMProviderProtocol,
        decision_engine: DecisionEngineProtocol,
        session_window_size: int,
        query_rewriter: QueryRewriter | None = None,
        planner_prefilter: PlannerPrefilter | None = None,
        defer_index_on_ignore: bool = True,
        uow: UnitOfWorkProtocol | None = None,
    ) -> None:
        self._messages = messages
        self._users = users
        self._turn_query = turn_query
        self._context_retriever = context_retriever
        self._indexing = indexing
        self._llm = llm
        self._decision_engine = decision_engine
        self._query_rewriter = query_rewriter or QueryRewriter(use_llm=False)
        self._planner_prefilter = planner_prefilter
        self._session_window_size = session_window_size
        self._defer_index_on_ignore = defer_index_on_ignore
        self._uow = uow

    async def _release_db_before_slow_io(self) -> None:
        if self._uow is not None:
            await self._uow.commit()

    async def handle_incoming(self, turn: ChatTurnInput) -> ConversationTurnResult:
        started = time.perf_counter()

        user = await self._users.get_or_create(
            telegram_id=turn.sender_telegram_id,
            username=turn.sender_username,
            first_name=turn.sender_first_name,
            last_name=turn.sender_last_name,
        )
        sender_name = resolve_user_display_name(
            turn.sender_telegram_id,
            nickname=user.nickname,
            first_name=user.first_name or turn.sender_first_name,
            username=user.username or turn.sender_username,
        )

        user_msg = await self._messages.create(
            role="user",
            content=turn.message,
            sender_telegram_id=turn.sender_telegram_id,
        )

        recent = [
            stored_to_context(message)
            for message in await self._messages.get_recent(
                limit=self._session_window_size,
            )
        ]

        plan_ms = 0.0
        if (
            settings.decision_planner_prefilter
            and self._planner_prefilter is not None
        ):
            prefilter = self._planner_prefilter.evaluate(
                turn.message,
                recent,
                mentions_bot=turn.mentions_bot,
                reply_to_bot=turn.reply_to_bot,
            )
            if not prefilter.run_planner:
                logger.info(
                    "turn_stage prefilter request_id=%s reason=%s action=ignore",
                    get_request_id(),
                    prefilter.reason,
                )
                if self._defer_index_on_ignore:
                    self._indexing.schedule(user_msg)
                else:
                    await self._indexing.index_now(user_msg)
                result = ConversationTurnResult(
                    action=DecisionAction.IGNORE.value,
                    reason=(
                        DecisionReason.DISMISSAL.value
                        if prefilter.reason == "dismissal"
                        else DecisionReason.PREFILTER.value
                    ),
                )
                logger.info(
                    "turn_processed request_id=%s chat_id=%s sender_id=%s action=%s "
                    "reason=%s planner_skipped=true total_ms=%.1f",
                    get_request_id(),
                    turn.telegram_chat_id,
                    turn.sender_telegram_id,
                    result.action,
                    result.reason,
                    (time.perf_counter() - started) * 1000,
                )
                return result

        rewrite_started = time.perf_counter()
        in_listen_window = in_post_reply_listen_window(
            recent,
            max_messages=settings.decision_post_reply_listen_count,
        )
        turn_plan = await self._query_rewriter.prepare(
            turn.message,
            recent_messages=recent,
            mentions_bot=turn.mentions_bot,
            reply_to_bot=turn.reply_to_bot,
            in_listen_window=in_listen_window,
        )
        plan_ms = (time.perf_counter() - rewrite_started) * 1000

        decision_started = time.perf_counter()
        decision = await self._decision_engine.decide(
            text=turn.message,
            telegram_chat_id=turn.telegram_chat_id,
            recent_messages=recent,
            search_text=turn_plan.text if not turn_plan.skip_search else "",
            should_reply=turn_plan.should_reply,
            mentions_bot=turn.mentions_bot,
            reply_to_bot=turn.reply_to_bot,
            in_listen_window=in_listen_window,
        )
        decision_ms = (time.perf_counter() - decision_started) * 1000

        logger.info(
            "turn_stage plan request_id=%s search=%r skip=%s should_reply=%s "
            "humor_ok=%s humor_query=%r plan_ms=%.1f decision_ms=%.1f "
            "action=%s reason=%s",
            get_request_id(),
            turn_plan.text,
            turn_plan.skip_search,
            turn_plan.should_reply,
            turn_plan.humor_ok,
            turn_plan.humor_query,
            plan_ms,
            decision_ms,
            decision.action.value,
            decision.reason.value,
        )

        if decision.action == DecisionAction.IGNORE:
            if self._defer_index_on_ignore:
                self._indexing.schedule(user_msg)
            else:
                await self._indexing.index_now(user_msg)
            result = ConversationTurnResult(
                action=decision.action.value,
                reason=decision.reason.value,
                relevance_score=decision.relevance_score,
            )
            logger.info(
                "turn_processed request_id=%s chat_id=%s sender_id=%s action=%s "
                "reason=%s relevance=%.3f search=%r skip=%s rewrite_ms=%.1f "
                "decision_ms=%.1f total_ms=%.1f",
                get_request_id(),
                turn.telegram_chat_id,
                turn.sender_telegram_id,
                result.action,
                result.reason,
                result.relevance_score,
                turn_plan.text,
                turn_plan.skip_search,
                plan_ms,
                decision_ms,
                (time.perf_counter() - started) * 1000,
            )
            return result

        await self._release_db_before_slow_io()

        query_vector: list[float] | None = None
        embed_ms = 0.0
        rag_plan = build_main_rag_plan(turn.message, turn_plan)
        if not turn_plan.skip_search and rag_plan.semantic_queries:
            embed_started = time.perf_counter()
            embed_ms = (time.perf_counter() - embed_started) * 1000
            logger.info(
                "turn_stage embed request_id=%s semantic=%r fts=%r embed_ms=%.1f",
                get_request_id(),
                rag_plan.semantic_queries,
                rag_plan.fts_query,
                embed_ms,
            )

        rag_started = time.perf_counter()
        context_blocks = await self._context_retriever.search(
            query=turn_plan.text or turn.message,
            query_vector=query_vector,
            semantic_queries=list(rag_plan.semantic_queries),
            fts_query=rag_plan.fts_query,
            skip_fts=turn_plan.skip_search,
        )
        rag_ms = (time.perf_counter() - rag_started) * 1000
        context_count = context_block_message_count(context_blocks)

        humor_quotes: list[str] = []
        humor_rag_ms = 0.0
        if turn_plan.humor_ok and turn_plan.humor_query.strip():
            humor_started = time.perf_counter()
            humor_vector = await self._turn_query.embed_query(turn_plan.humor_query)
            humor_blocks = await self._context_retriever.search(
                query=turn_plan.humor_query,
                query_vector=humor_vector,
                fts_query=f"{turn_plan.humor_query} мем подкол шутка",
                top_k=settings.rag_humor_top_k,
                anchor_max=settings.rag_humor_anchor_max,
                window_before=settings.rag_humor_window_before,
                window_after=settings.rag_humor_window_after,
            )
            humor_quotes = extract_humor_quotes(
                humor_blocks,
                max_quotes=settings.rag_humor_max_quotes,
                min_score=settings.rag_humor_min_quote_score,
            )
            humor_rag_ms = (time.perf_counter() - humor_started) * 1000
            logger.info(
                "turn_stage humor_rag request_id=%s humor_query=%r quotes=%s "
                "humor_rag_ms=%.1f",
                get_request_id(),
                turn_plan.humor_query,
                len(humor_quotes),
                humor_rag_ms,
            )

        logger.info(
            "turn_stage rag request_id=%s context=%s rag_ms=%.1f",
            get_request_id(),
            context_count,
            rag_ms,
        )

        llm_started = time.perf_counter()
        session_messages = session_context_messages(recent)
        reply = await self._llm.generate(
            user_message=turn.message,
            context_blocks=context_blocks,
            session_messages=session_messages,
            humor_quotes=humor_quotes or None,
            sender_telegram_id=turn.sender_telegram_id,
            sender_name=sender_name,
        )
        llm_ms = (time.perf_counter() - llm_started) * 1000
        logger.info(
            "turn_stage llm request_id=%s reply_len=%s llm_ms=%.1f",
            get_request_id(),
            len(reply),
            llm_ms,
        )

        if self._defer_index_on_ignore:
            self._indexing.schedule(user_msg)
        else:
            await self._indexing.index_now(user_msg)

        await self._messages.create(
            role="assistant",
            content=reply,
        )
        self._decision_engine.record_reply(turn.telegram_chat_id)

        result = ConversationTurnResult(
            action=decision.action.value,
            reason=decision.reason.value,
            reply=reply,
            context_count=context_count,
            relevance_score=decision.relevance_score,
        )
        logger.info(
            "turn_processed request_id=%s chat_id=%s sender_id=%s action=%s "
            "reason=%s relevance=%.3f search=%r skip=%s humor_quotes=%s "
            "context=%s plan_ms=%.1f embed_ms=%.1f decision_ms=%.1f "
            "rag_ms=%.1f humor_rag_ms=%.1f llm_ms=%.1f total_ms=%.1f",
            get_request_id(),
            turn.telegram_chat_id,
            turn.sender_telegram_id,
            result.action,
            result.reason,
            result.relevance_score,
            turn_plan.text,
            turn_plan.skip_search,
            len(humor_quotes),
            result.context_count,
            plan_ms,
            embed_ms,
            decision_ms,
            rag_ms,
            humor_rag_ms,
            llm_ms,
            (time.perf_counter() - started) * 1000,
        )
        return result
