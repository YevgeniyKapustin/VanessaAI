import asyncio

from fastapi import APIRouter, Response
from sqlalchemy import text

from vanessa.infrastructure.db.session import engine

router = APIRouter()

# Readiness probe must not hang the orchestrator/proxy: bound the DB round-trip.
_READINESS_TIMEOUT = 2.0


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness: the process is up and serving HTTP. Never does I/O.

    This is what the Docker HEALTHCHECK and load balancer use to decide the
    container is alive. A bare ``200`` with ``{"status": "ok"}`` keeps the
    historical contract.
    """
    return {"status": "ok"}


@router.get("/health/live")
async def liveness_check() -> dict[str, str]:
    """Explicit liveness alias for orchestrators that expect /health/live."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness_check(response: Response) -> dict[str, str]:
    """Readiness: the app can actually serve requests (DB reachable).

    The proxy/load-balancer only sends traffic here once this returns 200, so a
    freshly started container never receives requests before its dependencies
    (Postgres/Qdrant) are ready. Returns 503 while dependencies are down.
    """
    try:
        async with asyncio.timeout(_READINESS_TIMEOUT):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
    except Exception:
        response.status_code = 503
        return {"status": "unavailable"}
    return {"status": "ready"}
