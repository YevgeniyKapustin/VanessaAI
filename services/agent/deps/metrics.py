from services.agent.deps.access import get_container
from vanessa.core.protocols import TurnMetricsProtocol


def get_turn_metrics(request) -> TurnMetricsProtocol:
    return get_container(request).graph.metrics.turn_metrics()
