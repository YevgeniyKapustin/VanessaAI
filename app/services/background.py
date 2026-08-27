"""Bounded background executor for non-critical post-reply work.

The chat reply path must never wait on embedding-heavy or slow auxiliary work
(memory extraction, metrics snapshots, message indexing). This executor runs
such jobs on a small pool of worker tasks behind a bounded queue; when the
queue is full, new jobs are dropped (fail-open) instead of blocking the caller.
"""

from __future__ import annotations

import asyncio
import logging

from app.observability.metrics import record_background_queue

logger = logging.getLogger(__name__)

Job = object  # a zero-arg async callable


class BackgroundExecutor:
    def __init__(self, *, maxsize: int = 200, workers: int = 2) -> None:
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._worker_count = max(1, workers)
        self._workers: list[asyncio.Task] = []
        self._started = False

    def start(self) -> None:
        """Spawn the worker tasks. Must be called from a running event loop."""
        if self._started:
            return
        self._started = True
        loop = asyncio.get_running_loop()
        self._workers = [
            loop.create_task(self._run(name)) for name in range(self._worker_count)
        ]
        logger.info("background_executor_started workers=%s", self._worker_count)

    async def _run(self, name: int) -> None:
        while True:
            job = await self._queue.get()
            try:
                try:
                    await job()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("background_job_failed worker=%s", name)
            finally:
                self._queue.task_done()
                record_background_queue(self._queue.qsize())

    def submit(self, job) -> None:
        """Schedule a zero-arg async callable; drop it when the queue is full."""
        if not self._started:
            logger.warning("background_executor_not_started dropping job")
            return
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull:
            logger.warning("background_queue_full dropping job")
        record_background_queue(self._queue.qsize())

    async def join(self) -> None:
        """Wait until every submitted job has finished (test/teardown aid)."""
        await self._queue.join()

    async def shutdown(self) -> None:
        self._started = False
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        logger.info("background_executor_shutdown")
