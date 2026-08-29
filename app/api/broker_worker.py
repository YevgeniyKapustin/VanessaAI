"""Agent-core broker worker.

Active when ``settings.transport == "redis"``: consumes ``TurnRequest``
messages from the broker, runs the exact same Gate → Retrieve → Compose →
Finalize pipeline as the HTTP path (via ``build_orchestrator``),
and publishes ``TurnStarted`` (typing) + ``TurnReply`` to the request's
private reply stream.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from app.broker.backends import Delivery
from app.contracts.messages import TurnReply, TurnRequest, TurnStarted
from app.core.messages import ImageAttachment
from app.core.protocols import IncomingTurnHandlerProtocol
from app.core.request_context import (
    request_id_var,
    set_planning_started_signal,
)
from app.core.turn import ChatTurnInput, ConversationTurnResult
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

#: Builds the per-turn pipeline handler from a fresh DB session.
HandlerBuilder = Callable[[Any], IncomingTurnHandlerProtocol]


def default_handler_builder(session) -> IncomingTurnHandlerProtocol:
    """Assemble the real pipeline for one turn (runs inside the API process)."""
    from app.api import deps
    from app.api.container import get_app_container
    from app.config import settings
    from app.db.repository import MessageRepository, UserRepository
    from app.db.session import async_session_factory
    from app.services.indexing.message_indexing import MessageIndexingService
    from app.services.turn_metrics import turn_metrics

    messages = MessageRepository(session)
    users = UserRepository(session)
    embeddings = deps.create_embedding_provider()
    vector_store = deps.create_vector_store()
    hybrid = deps.create_hybrid_search(messages, embeddings, vector_store)
    indexing = MessageIndexingService(
        indexer=hybrid,
        messages=messages,
        session_factory=async_session_factory,
        max_retries=settings.indexing_max_retries,
        background=get_app_container().background,
        dispatcher=deps.get_task_dispatcher(),
    )
    llm = deps.create_llm_provider()
    decision = deps.create_decision_engine(embeddings, vector_store)
    query_rewriter = deps.create_query_rewriter()
    uow = deps.SqlAlchemyUnitOfWork(session)
    web_search = deps.create_web_search()
    return deps.build_orchestrator(
        messages,
        users,
        hybrid,
        indexing,
        llm,
        decision,
        query_rewriter,
        uow,
        turn_metrics,
        web_search,
    )


class BrokerTurnWorker:
    """Consumes turns from the broker and runs the orchestrator pipeline."""

    def __init__(
        self,
        broker,
        *,
        stream: str,
        group: str,
        consumer: str,
        handler_builder: HandlerBuilder | None = None,
        dedup=None,
    ) -> None:
        self._broker = broker
        self._stream = stream
        self._group = group
        self._consumer = consumer
        self._handler_builder = handler_builder or default_handler_builder
        self._dedup = dedup

    async def run_forever(self) -> None:
        await self._broker.consume_forever(
            self._stream,
            self._group,
            self._consumer,
            self._handle,
            dedup=self._dedup,
        )

    async def _handle(self, delivery: Delivery) -> None:
        request = delivery.message
        if not isinstance(request, TurnRequest):
            logger.warning(
                "broker_unexpected_message kind=%s stream=%s",
                request.message_kind(),
                delivery.stream,
            )
            return
        # Propagate the transport's request id so pipeline logs/spans line up
        # with the bot's original request (the HTTP path sets the same id via
        # the X-Request-ID middleware).
        request_id_var.set(request.correlation_id)
        turn = self._to_turn(request)

        async def signal_started() -> None:
            if request.reply_to:
                await self._broker.publish(
                    request.reply_to,
                    TurnStarted(
                        correlation_id=request.correlation_id,
                        trace_id=request.trace_id,
                    ),
                )

        set_planning_started_signal(signal_started)
        try:
            result = await self._run_pipeline(turn)
        finally:
            set_planning_started_signal(None)

        if not request.reply_to:
            return
        await self._broker.publish(
            request.reply_to,
            TurnReply(
                correlation_id=request.correlation_id,
                trace_id=request.trace_id,
                action=result.action,
                reason=result.reason,
                reply=result.reply,
                messages=result.messages,
                context_count=result.context_count,
                relevance_score=result.relevance_score,
                sticker_tag=result.sticker_tag,
                photo_file_id=result.photo_file_id,
                photo_data_url=result.photo_data_url,
            ),
        )

    async def _run_pipeline(self, turn: ChatTurnInput) -> ConversationTurnResult:
        # One fresh session + handler per turn, mirroring the HTTP request scope
        # (the request dependency commits the unit of work after the handler).
        async with async_session_factory() as session:
            handler = self._handler_builder(session)
            try:
                result = await handler.handle_incoming(turn)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise

    @staticmethod
    def _to_turn(request: TurnRequest) -> ChatTurnInput:
        return ChatTurnInput(
            telegram_chat_id=request.telegram_chat_id,
            message=request.message,
            sender_telegram_id=request.sender_telegram_id,
            chat_title=request.chat_title,
            chat_type=request.chat_type,
            sender_username=request.sender_username,
            sender_first_name=request.sender_first_name,
            sender_last_name=request.sender_last_name,
            mentions_bot=request.mentions_bot,
            reply_to_bot=request.reply_to_bot,
            reply_to_other_user=request.reply_to_other_user,
            reply_to_sender_telegram_id=request.reply_to_sender_telegram_id,
            reply_to_message_id=request.reply_to_message_id,
            reply_to_text=request.reply_to_text,
            reply_to_sender_name=request.reply_to_sender_name,
            images=tuple(
                ImageAttachment(
                    data_url=image.data_url,
                    mime_type=image.mime_type,
                    telegram_file_id=image.telegram_file_id,
                )
                for image in request.images
            ),
        )
