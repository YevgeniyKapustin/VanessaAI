"""Wait for a Hermes run to finish, with deny-and-stop for human prompts."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from vanessa.infrastructure.hermes.client import HermesClient
from vanessa.infrastructure.hermes.models import HermesRun, HermesUnavailableError

logger = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


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
    sleep: Sleep = asyncio.sleep,
    clock: Clock = time.monotonic,
) -> str | None:
    """Poll ``run_id`` until it ends; return the answer or None.

    A run that asks for approval or clarification is stopped: nobody in a
    group chat may approve actions on the owner's PC. A run past
    ``max_wait_seconds`` is stopped too.
    """
    deadline = clock() + max_wait_seconds
    while True:
        run = await client.get_run(run_id)
        if run.is_terminal:
            return _answer(run)
        if run.needs_human or clock() >= deadline:
            logger.info("hermes_run_stopped run_id=%s status=%s", run_id, run.status)
            await _stop_quietly(client, run_id)
            return None
        await sleep(poll_seconds)


def _answer(run: HermesRun) -> str | None:
    if not run.is_completed or not run.output:
        logger.info("hermes_run_no_answer run_id=%s status=%s", run.run_id, run.status)
        return None
    return run.output
