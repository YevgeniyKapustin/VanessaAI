"""Wait for a Hermes run to finish, with deny-and-stop for human prompts.

The result says *why* a run ended without an answer (``failure``), so the
follow-up can name the reason instead of shrugging. ``on_progress`` fires once
when the run outlives ``progress_after_seconds``: the chat gets one line that
the lookup is still going, instead of minutes of silence.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from vanessa.infrastructure.hermes.client import HermesClient
from vanessa.infrastructure.hermes.models import (
    FAILURE_BLOCKED,
    FAILURE_TIMEOUT,
    HermesRun,
    HermesUnavailableError,
)

logger = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]
Progress = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class HermesWaitResult:
    """The answer, or no answer plus the reason code."""

    answer: str | None = None
    failure: str = ""


class _Progress:
    """Fires the one progress callback at most once."""

    def __init__(self, on_progress: Progress | None, after_seconds: float) -> None:
        self._cb = on_progress
        self._after = after_seconds
        self._done = False

    async def maybe(self, elapsed: float) -> None:
        if self._done:
            return
        if not self._wanted(elapsed):
            return
        self._done = True
        await self._cb()

    def _wanted(self, elapsed: float) -> bool:
        return self._after > 0 and self._cb is not None and elapsed >= self._after


async def _stop_quietly(client: HermesClient, run_id: str) -> None:
    try:
        await client.stop_run(run_id)
    except HermesUnavailableError:
        logger.warning("hermes_stop_failed run_id=%s", run_id)


async def wait_for_output(
    client: HermesClient,
    run_id: str,
    *,
    poll_seconds: float,
    max_wait_seconds: float,
    progress_after_seconds: float = 0.0,
    on_progress: Progress | None = None,
    sleep: Sleep = asyncio.sleep,
    clock: Clock = time.monotonic,
) -> HermesWaitResult:
    """Poll ``run_id`` until it ends; return the answer or the failure code.

    A run that asks for approval or clarification is stopped: nobody in a
    group chat may approve actions on the owner's PC. A run past
    ``max_wait_seconds`` is stopped too.
    """
    started = clock()
    deadline = started + max_wait_seconds
    progress = _Progress(on_progress, progress_after_seconds)
    while True:
        run = await client.get_run(run_id)
        if run.is_terminal:
            return _result(run)
        now = clock()
        failure = _stop_failure(run, now, deadline)
        if failure:
            logger.info("hermes_run_stopped run_id=%s status=%s", run_id, run.status)
            await _stop_quietly(client, run_id)
            return HermesWaitResult(failure=failure)
        await progress.maybe(now - started)
        await sleep(poll_seconds)


def _stop_failure(run: HermesRun, now: float, deadline: float) -> str:
    """Why this poll must stop the run; empty while it should keep going."""
    if run.needs_human:
        return FAILURE_BLOCKED
    if now >= deadline:
        return FAILURE_TIMEOUT
    return ""


def _result(run: HermesRun) -> HermesWaitResult:
    if not run.is_completed or not run.output:
        logger.info("hermes_run_no_answer run_id=%s status=%s", run.run_id, run.status)
        return HermesWaitResult(failure=run.failure)
    return HermesWaitResult(answer=run.output)
