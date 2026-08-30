from __future__ import annotations

from services.agent.container.graph import ProcessGraph
from services.agent.container.role import ProcessRole
from services.agent.container.turns import TurnWiring


class AppContainer:
    def __init__(
        self,
        graph: ProcessGraph | None = None,
        turns: TurnWiring | None = None,
        role: ProcessRole | None = None,
    ) -> None:
        self.role = role or ProcessRole.from_settings()
        self.graph = graph or ProcessGraph(role=self.role)
        self.turns = turns or TurnWiring(self.graph, role=self.role)
