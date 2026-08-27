from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.config.settings import settings
from app.observability.metrics import CONTENT_TYPE_LATEST, render_metrics

router = APIRouter(tags=["observability"])


async def _metrics_guard(request: Request) -> None:
    """Optionally protect GET /metrics with the internal token.

    Prometheus can be configured to send it via ``scrape_configs`` →
    ``bearer_token``. Disabled by default so a stock Prometheus scrape works.
    """
    if not settings.metrics_require_token:
        return
    expected = settings.api_internal_token.strip()
    if not expected:
        return
    if request.headers.get("X-Internal-Token") != expected:
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
