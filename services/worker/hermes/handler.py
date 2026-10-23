"""``hermes_ask`` task handler: schedule a background Hermes job and return.

The worker consumes tasks one at a time, and a Hermes run can take up to
``hermes_max_wait_seconds``. So ``handle()`` never waits for Hermes: it
validates the payload, starts an asyncio job and returns (the task is
acked). A semaphore bounds the jobs that talk to Hermes at once; the rest
queue on it, up to ``max_queued``. Extra asks are dropped with a log.

Jobs live only in this process. A worker restart loses the jobs in
progress (the task is already acked, so it is not redelivered); the Hermes
run itself continues on the PC. This is accepted: the user gets no
follow-up for that ask.
"""

from __future__ import annotations

import asyncio
import logging

from services.worker.hermes.payload import HermesAsk, parse_hermes_ask
from services.worker.hermes.runner import HermesRunner
from vanessa.contracts.messages import TaskMessage
from vanessa.infrastructure.observability.metrics.metrics_hermes_jobs import (
    record_hermes_job,
)

logger = logging.getLogger(__name__)

# Queued jobs per parallel slot.
QUEUE_FACTOR = 3


class HermesAskHandler:
    def __init__(
        self, runner: HermesRunner, *, max_parallel: int, max_queued: int | None = None
    ) -> None:
        parallel = max(1, max_parallel)
        queued = QUEUE_FACTOR * parallel if max_queued is None else max(0, max_queued)
        self._runner = runner
        self._slots = asyncio.Semaphore(parallel)
        self._max_jobs = parallel + queued
        # Strong references: the event loop keeps only weak ones to tasks.
        self._jobs: set[asyncio.Task[None]] = set()

    @property
    def job_count(self) -> int:
        return len(self._jobs)

    async def handle(self, task: TaskMessage) -> None:
        ask = parse_hermes_ask(task)
        if ask is None:
            logger.warning("hermes_ask_invalid correlation_id=%s", task.correlation_id)
            return
        if len(self._jobs) >= self._max_jobs:
            logger.warning(
                "hermes_ask_dropped chat_id=%s jobs=%s",
                ask.telegram_chat_id,
                len(self._jobs),
            )
            record_hermes_job("dropped")
            return
        job = asyncio.create_task(self._guarded(ask), name=f"hermes:{ask.idempotency_key}")
        self._jobs.add(job)
        job.add_done_callback(self._jobs.discard)

    async def aclose(self) -> None:
        """Cancel every job (worker shutdown) and wait until they stop."""
        jobs = list(self._jobs)
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        if jobs:
            logger.info("hermes_jobs_cancelled count=%s", len(jobs))

    async def _guarded(self, ask: HermesAsk) -> None:
        async with self._slots:
            try:
                await self._runner.run(ask)
            except Exception as exc:  # noqa: BLE001 - a job must not kill the worker
                logger.warning(
                    "hermes_job_failed chat_id=%s error=%s",
                    ask.telegram_chat_id,
                    type(exc).__name__,
                )
                record_hermes_job("failed")
