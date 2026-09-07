from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from services.presence.container import create_presence_services, run_presence
from vanessa.core.logging_setup import configure_logging

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VanessaAI VRChat presence adapter")
    parser.add_argument("--avatar", type=Path, default=None)
    return parser.parse_args(argv)


async def async_main(argv: list[str] | None = None) -> None:
    configure_logging("presence")
    args = parse_args(argv)
    services = create_presence_services(avatar_path=args.avatar)
    logger.info(
        "presence started osc=%s:%s",
        services.avatar.osc.host,
        services.avatar.osc.port,
    )
    try:
        await run_presence(services)
    finally:
        await services.close()
        logger.info("presence shutdown complete")


def main() -> None:
    asyncio.run(async_main())
