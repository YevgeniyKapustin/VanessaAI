from vanessa.infrastructure.db.session import async_session_factory

from services.agent.broker_worker.handlers import TurnHandlerFactory
from services.agent.broker_worker.mapping import TurnMapper
from services.agent.broker_worker.pipeline import SessionPipeline
from services.agent.broker_worker.replies import ReplyPublisher
from services.agent.broker_worker.types import HandlerBuilder
from services.agent.broker_worker.worker import (
    BrokerTurnWorker,
    TurnDeliveryHandler,
)
from services.agent.container import AppContainer


def default_handler_builder(container: AppContainer):
    return TurnHandlerFactory(container).build


__all__ = [
    "BrokerTurnWorker",
    "HandlerBuilder",
    "ReplyPublisher",
    "SessionPipeline",
    "TurnDeliveryHandler",
    "TurnHandlerFactory",
    "TurnMapper",
    "async_session_factory",
    "default_handler_builder",
]
