"""Wait for a Hermes run to finish, with deny-and-stop for human prompts.

The result says *why* a run ended without an answer (``failure``), so the
follow-up can name the reason instead of shrugging. ``on_progress`` fires
again every ``progress_after_seconds``: a ten-minute job keeps telling the
chat it is alive instead of going quiet after one line. A run that crosses
``max_wait_seconds`` gets one final look before it is stopped, because a
poll can answer ``running`` a moment before the reply lands.
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
Progress = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class HermesWaitResult:
    """The answer, or no answer plus the reason code."""

    answer: str | None = None
    failure: str = ""


@dataclass(frozen=True, slots=True)
class _Poll:
    """One wait's budget: since when, until when, and how often."""

    started: float
    deadline: float
    interval: float
    sleep: Sleep
    clock: Clock


class _Progress:
    """Fires the progress callback again every ``after_seconds``."""

    def __init__(self, on_progress: Progress | None, after_seconds: float) -> None:
        self._cb = on_progress
        self._after = after_seconds
        self._next = after_seconds

    async def maybe(self, elapsed: float) -> None:
        if not self._wanted(elapsed):
            return
        self._next = elapsed + self._after
        await self._cb(elapsed)

    def _wanted(self, elapsed: float) -> bool:
        return self._after > 0 and self._cb is not None and elapsed >= self._next


async def _stop_quietly(client: HermesClient, run_id: str) -> None:
    try:
        await client.stop_run(run_id)
    except HermesUnavailableError:
        logger.warning("hermes_stop_failed run_id=%s", run_id)


async def _last_look(
    client: HermesClient, run_id: str, poll: _Poll
) -> HermesRun | None:
    """The run may finish while the deadline poll is in flight."""
    await poll.sleep(poll.interval)
    run = await client.get_run(run_id)
    return run if run.is_terminal else None


async def _stop_run(
    client: HermesClient, run_id: str, failure: str, poll: _Poll
) -> HermesWaitResult:
    """Stop the run and report why, after one last look when time ran out."""
    if failure == FAILURE_TIMEOUT:
        late = await _last_look(client, run_id, poll)
        if late is not None:
            return _result(late)
    logger.info("hermes_run_stopped run_id=%s failure=%s", run_id, failure)
    await _stop_quietly(client, run_id)
    return HermesWaitResult(failure=failure)


async def _poll_once(
    client: HermesClient, run_id: str, progress: _Progress, poll: _Poll
) -> HermesWaitResult | None:
    """One look at the run; None means keep waiting."""
    run = await client.get_run(run_id)
    if run.is_terminal:
        return _result(run)
    now = poll.clock()
    failure = _stop_failure(run, now, poll.deadline)
    if failure:
        return await _stop_run(client, run_id, failure, poll)
    await progress.maybe(now - poll.started)
    return None


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
    poll = _Poll(
        started=started,
        deadline=started + max_wait_seconds,
        interval=poll_seconds,
        sleep=sleep,
        clock=clock,
    )
    progress = _Progress(on_progress, progress_after_seconds)
    while True:
        outcome = await _poll_once(client, run_id, progress, poll)
        if outcome is not None:
            return outcome
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
