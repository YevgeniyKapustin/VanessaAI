"""Agent process: broker turns + health/metrics HTTP.

    python -m services.agent.main
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from services.agent.container import AppContainer
from services.agent.lifespan import lifespan
from vanessa.config import settings
from vanessa.core.logging_setup import configure_logging
from vanessa.infrastructure.db.session import engine
from vanessa.infrastructure.observability.metrics import start_metrics_http_server

logger = logging.getLogger(__name__)


def postgres_ready() -> bool:
    try:
        with engine.sync_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


async def run(*, container: AppContainer | None = None) -> None:
    configure_logging("agent")
    owned = container or AppContainer()
    start_metrics_http_server(
        settings.api_port,
        addr=settings.api_host,
        ready_check=postgres_ready,
    )
    logger.info("agent health/metrics on :%s", settings.api_port)
    async with lifespan(owned):
        await asyncio.Event().wait()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
