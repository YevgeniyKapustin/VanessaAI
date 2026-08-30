from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from vanessa.observability.metrics import (
    CONTENT_TYPE_LATEST,
    metrics_token_allowed,
    render_metrics,
)

router = APIRouter(tags=["observability"])


async def _metrics_guard(request: Request) -> None:
    """Protect GET /metrics when METRICS_REQUIRE_TOKEN is on."""
    if metrics_token_allowed(request.headers):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid internal API token",
    )


@router.get(
    "/metrics",
    dependencies=[Depends(_metrics_guard)],
    include_in_schema=False,
)
async def metrics_endpoint() -> Response:
    return Response(
        content=render_metrics(),
        media_type=CONTENT_TYPE_LATEST,
    )
