from fastapi import FastAPI

from services.agent.routes import health, metrics, observability

_ROUTERS = (
    health.router,
    metrics.router,
    observability.router,
)


def register_routes(app: FastAPI) -> None:
    for router in _ROUTERS:
        app.include_router(router)
