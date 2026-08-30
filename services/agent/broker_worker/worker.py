from __future__ import annotations

import logging

from services.agent.broker_worker.handlers import TurnHandlerFactory
from services.agent.broker_worker.mapping import TurnMapper
from services.agent.broker_worker.pipeline import SessionPipeline
from services.agent.broker_worker.replies import ReplyPublisher
from services.agent.broker_worker.types import HandlerBuilder
from vanessa.contracts.messages import TurnRequest
from vanessa.core.request_context import (
    request_id_var,
    set_planning_started_signal,
)
from vanessa.infrastructure.broker.backends import Delivery
from vanessa.infrastructure.db.session import async_session_factory

logger = logging.getLogger(__name__)


class TurnDeliveryHandler:
    def __init__(
        self,
        mapper: TurnMapper,
        pipeline: SessionPipeline,
        replies: ReplyPublisher,
    ) -> None:
        self._mapper = mapper
        self._pipeline = pipeline
        self._replies = replies

    async def handle(self, delivery: Delivery) -> None:
        request = delivery.message
        if not isinstance(request, TurnRequest):
            logger.warning(
                "broker_unexpected_message kind=%s stream=%s",
                request.message_kind(),
                delivery.stream,
            )
            return
        request_id_var.set(request.correlation_id)
        turn = self._mapper.to_turn(request)
        set_planning_started_signal(lambda: self._replies.started(request))
        try:
            result = await self._pipeline.run(turn)
        finally:
            set_planning_started_signal(None)
        await self._replies.reply(request, result)


class BrokerTurnWorker:
    def __init__(
        self,
        broker,
        *,
        stream: str,
        group: str,
        consumer: str,
        handler_builder: HandlerBuilder | None = None,
        session_factory=None,
        mapper: TurnMapper | None = None,
        replies: ReplyPublisher | None = None,
        pipeline: SessionPipeline | None = None,
        deliveries: TurnDeliveryHandler | None = None,
        handlers: TurnHandlerFactory | None = None,
        dedup=None,
    ) -> None:
        self._broker = broker
        self._stream = stream
        self._group = group
        self._consumer = consumer
        self._dedup = dedup
        if handler_builder is not None:
            builder = handler_builder
        elif handlers is not None:
            builder = handlers.build
        else:
            raise TypeError("handler_builder or handlers is required")
        factory = session_factory or async_session_factory
        self._mapper = mapper or TurnMapper()
        self._replies = replies or ReplyPublisher(broker)
        self._pipeline = pipeline or SessionPipeline(factory, builder)
        self._deliveries = deliveries or TurnDeliveryHandler(
            self._mapper,
            self._pipeline,
            self._replies,
        )

    async def run_forever(self) -> None:
        await self._broker.consume_forever(
            self._stream,
            self._group,
            self._consumer,
            self._deliveries.handle,
            dedup=self._dedup,
        )

    async def _handle(self, delivery: Delivery) -> None:
        await self._deliveries.handle(delivery)
