from __future__ import annotations

from services.agent.container.decision.decision_factory import DecisionFactory
from services.agent.container.graph import ProcessGraph
from services.agent.container.role import ProcessRole
from services.agent.container.turns.engines import TurnEngines
from services.agent.container.turns.orchestrator import OrchestratorFactory
from services.agent.container.turns.persistence import Persistence
from services.agent.container.turns.search import Search
from vanessa.core.protocols import IncomingTurnHandlerProtocol


class TurnWiring:
    def __init__(
        self,
        graph: ProcessGraph,
        *,
        persistence: Persistence | None = None,
        search: Search | None = None,
        decision_factory: DecisionFactory | None = None,
        orchestrator: OrchestratorFactory | None = None,
        role: ProcessRole | None = None,
    ) -> None:
        self.graph = graph
        self.role = role or ProcessRole.from_settings()
        self.persistence = persistence or Persistence()
        self.search = search or Search(graph)
        self.decision_factory = decision_factory or DecisionFactory(graph)
        self.orchestrator = orchestrator or OrchestratorFactory(graph)
        self._engines: TurnEngines | None = None

    def engines(self) -> TurnEngines:
        if self._engines is None:
            self._engines = TurnEngines.build(
                self.graph,
                self.role,
                self.search,
                self.decision_factory,
            )
        return self._engines

    def handler(self, session) -> IncomingTurnHandlerProtocol:
        graph = self.graph
        messages = self.persistence.messages(session)
        users = self.persistence.users(session)
        return self.orchestrator.build(
            messages,
            users,
            self.persistence.unit_of_work(session),
            graph.metrics.turn_metrics(),
            self.engines(),
        )
