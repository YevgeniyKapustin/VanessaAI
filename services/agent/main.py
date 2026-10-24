"""Agent process: broker turns + health/metrics HTTP.

    python -m services.agent.main
"""

from __future__ import annotations

import asyncio
import logging

import asyncpg

from services.agent.container import AppContainer
from services.agent.lifespan import lifespan
from vanessa.config import settings
from vanessa.core.logging_setup import configure_logging
from vanessa.infrastructure.db.locked_upgrade import _dsn
from vanessa.infrastructure.observability.metrics import start_metrics_http_server
from vanessa.infrastructure.observability.trace_log import configure_trace_log

logger = logging.getLogger(__name__)


async def _ping_postgres() -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute("SELECT 1")
    finally:
        await conn.close()


def postgres_ready() -> bool:
    # Probe thread: do not use the shared async engine (wrong event loop).
    try:
        asyncio.run(_ping_postgres())
        return True
    except Exception:  # noqa: BLE001
        return False


async def run(*, container: AppContainer | None = None) -> None:
    configure_logging("agent")
    configure_trace_log("agent")
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
