from services.agent.container import AppContainer
from vanessa.core.protocols import IncomingTurnHandlerProtocol


class TurnHandlerFactory:
    def __init__(self, container: AppContainer) -> None:
        self._container = container

    def build(self, session) -> IncomingTurnHandlerProtocol:
        return self._container.turns.handler(session)
