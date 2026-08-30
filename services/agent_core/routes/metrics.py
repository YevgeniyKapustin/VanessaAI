from fastapi import APIRouter, Depends

from services.agent_core.auth import verify_internal_token
from services.agent_core.deps import get_turn_metrics
from vanessa.core.protocols import TurnMetricsProtocol

router = APIRouter(dependencies=[Depends(verify_internal_token)])


@router.get("/metrics")
async def get_turn_metrics_route(
    metrics: TurnMetricsProtocol = Depends(get_turn_metrics),
) -> dict:
    snapshot = metrics.snapshot()
    return {
        "total": snapshot.total,
        "replies": snapshot.replies,
        "ignores": snapshot.ignores,
        "planner_skipped": snapshot.planner_skipped,
        "deep_search_used": snapshot.deep_search_used,
        "by_reason": snapshot.by_reason,
        "by_action_reason": snapshot.by_action_reason,
    }


@router.post("/metrics/reset")
async def reset_turn_metrics_route(
    metrics: TurnMetricsProtocol = Depends(get_turn_metrics),
) -> dict:
    metrics.reset()
    return {"status": "ok"}
