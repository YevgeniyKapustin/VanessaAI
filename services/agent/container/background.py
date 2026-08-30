from __future__ import annotations

from vanessa.config.settings import settings
from vanessa.pipeline.background import BackgroundExecutor


class BackgroundJobs:
    def __init__(self, executor: BackgroundExecutor | None = None) -> None:
        self.executor = executor or BackgroundExecutor(
            maxsize=settings.background_queue_size,
            workers=settings.background_workers,
        )

    def start(self) -> None:
        self.executor.start()

    async def shutdown(self) -> None:
        await self.executor.shutdown()
