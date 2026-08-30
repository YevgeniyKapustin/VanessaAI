from fastapi import Request

from services.agent.deps.access import get_container
from vanessa.core.protocols import TurnMetricsProtocol


def get_turn_metrics(request: Request) -> TurnMetricsProtocol:
    return get_container(request).graph.metrics.turn_metrics()
