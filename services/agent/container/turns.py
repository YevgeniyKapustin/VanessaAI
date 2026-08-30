from __future__ import annotations

from services.agent.container.decision_factory import DecisionFactory
from services.agent.container.engines import TurnEngines
from services.agent.container.graph import ProcessGraph
from services.agent.container.indexing import Indexing
from services.agent.container.orchestrator import OrchestratorFactory
from services.agent.container.persistence import Persistence
from services.agent.container.role import ProcessRole
from services.agent.container.search import Search
from vanessa.core.protocols import IncomingTurnHandlerProtocol


class TurnWiring:
    def __init__(
        self,
        graph: ProcessGraph,
        persistence: Persistence | None = None,
        search: Search | None = None,
        indexing: Indexing | None = None,
        decision_factory: DecisionFactory | None = None,
        orchestrator: OrchestratorFactory | None = None,
        role: ProcessRole | None = None,
    ) -> None:
        self.graph = graph
        self.role = role or ProcessRole.from_settings()
        self.persistence = persistence or Persistence()
        self.search = search or Search(graph)
        self.indexing = indexing or Indexing(graph)
        self.decision_factory = decision_factory or DecisionFactory(graph)
        self.orchestrator = orchestrator or OrchestratorFactory(graph, self)
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
        embeddings = graph.retrieval.embeddings
        vector_store = graph.retrieval.indexes.messages
        hybrid = self.search.hybrid(messages, embeddings, vector_store)
        indexing = self.indexing.messages(messages, hybrid)
        return self.orchestrator.build(
            messages,
            users,
            hybrid,
            indexing,
            self.persistence.unit_of_work(session),
            graph.metrics.turn_metrics(),
            self.engines(),
        )
