"""PortraitWorker: background loop over PortraitBuilder."""

from __future__ import annotations

import asyncio
import logging

from vanessa.knowledge.portraits.portraits import PortraitBuilder

logger = logging.getLogger(__name__)


class PortraitWorker:
    """Background loop that periodically refreshes stale person portraits."""

    def __init__(
        self,
        builder: PortraitBuilder,
        *,
        poll_seconds: int = 300,
    ) -> None:
        self._builder = builder
        self._poll = max(1, poll_seconds)

    async def run_forever(self) -> None:
        while True:
            try:
                updated = await self._builder.run()
                if updated:
                    logger.info("portrait_worker_cycle updated=%s", updated)
            except Exception:
                logger.exception("portrait_worker_cycle_failed")
            await asyncio.sleep(self._poll)
