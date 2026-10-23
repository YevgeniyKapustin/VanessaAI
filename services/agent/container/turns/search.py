from services.agent.container.graph import ProcessGraph
from vanessa.knowledge.people.participants import ParticipantsDigest
from vanessa.pipeline.llm.planner.turn_planner import TurnPlanner


class Search:
    def __init__(
        self,
        graph: ProcessGraph,
        participants: ParticipantsDigest | None = None,
    ) -> None:
        self._graph = graph
        self._participants = participants

    def participants_digest(self) -> ParticipantsDigest:
        if self._participants is None:
            knowledge = self._graph.knowledge
            self._participants = ParticipantsDigest(
                knowledge.vault,
                knowledge.index,
            )
        return self._participants

    def query_rewriter(self) -> TurnPlanner:
        return TurnPlanner(
            participants_provider=self.participants_digest().build,
        )
