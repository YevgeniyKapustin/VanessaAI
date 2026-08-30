"""Serialize ``alembic upgrade`` with a Postgres session advisory lock.

Safe as a Kubernetes init container on multiple replicas: waiters block,
then no-op if the schema is already at head.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from urllib.parse import quote_plus

import asyncpg

from vanessa.config import settings

logger = logging.getLogger(__name__)

# Stable 64-bit key; not a secret.
_LOCK_KEY = 0x56414E4553534131  # "VANESSA1"


def _dsn() -> str:
    user = quote_plus(settings.postgres_user)
    password = quote_plus(settings.postgres_password)
    return (
        f"postgresql://{user}:{password}@"
        f"{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )


async def _upgrade() -> int:
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", _LOCK_KEY)
        logger.info("alembic advisory lock acquired")
        proc = await asyncio.create_subprocess_exec("alembic", "upgrade", "head")
        code = await proc.wait()
        if code != 0:
            logger.error("alembic upgrade exited %s", code)
        return code
    finally:
        try:
            await conn.execute("SELECT pg_advisory_unlock($1)", _LOCK_KEY)
        finally:
            await conn.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(asyncio.run(_upgrade()))


if __name__ == "__main__":
    main()
