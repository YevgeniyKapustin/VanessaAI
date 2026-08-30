from vanessa.core.protocols import TurnMetricsProtocol
from vanessa.pipeline.turn_metrics import turn_metrics


class Metrics:
    def __init__(self, turn: TurnMetricsProtocol | None = None) -> None:
        self._turn = turn or turn_metrics

    def turn_metrics(self) -> TurnMetricsProtocol:
        return self._turn
