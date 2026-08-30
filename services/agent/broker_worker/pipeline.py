from services.agent.broker_worker.types import HandlerBuilder
from vanessa.core.turn import ChatTurnInput, ConversationTurnResult


class SessionPipeline:
    def __init__(self, session_factory, handler_builder: HandlerBuilder) -> None:
        self._session_factory = session_factory
        self._handler_builder = handler_builder

    async def run(self, turn: ChatTurnInput) -> ConversationTurnResult:
        async with self._session_factory() as session:
            handler = self._handler_builder(session)
            try:
                result = await handler.handle_incoming(turn)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
