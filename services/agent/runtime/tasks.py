from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial

logger = logging.getLogger(__name__)

Factory = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class _Spawned:
    task: asyncio.Task
    name: str
    log_stop: bool


def _log_death(name: str, task: asyncio.Task) -> None:
    """A background loop that stopped is an outage: never let it pass silently."""
    if task.cancelled():
        return
    error = task.exception()
    if error is None:
        logger.error("%s exited on its own; that loop is no longer running", name)
        return
    logger.error("%s died: %r", name, error, exc_info=error)


async def _run_once(factory: Factory, *, name: str, restart_seconds: float) -> None:
    try:
        await factory()
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # a crashed loop is restarted, never fatal
        logger.exception(
            "%s crashed: %r; restarting in %.1fs", name, exc, restart_seconds
        )
    else:
        logger.error("%s returned; restarting in %.1fs", name, restart_seconds)


async def _restart_forever(
    factory: Factory, *, name: str, restart_seconds: float
) -> None:
    while True:
        await _run_once(factory, name=name, restart_seconds=restart_seconds)
        await asyncio.sleep(restart_seconds)


class TaskSet:
    def __init__(self) -> None:
        self._items: list[_Spawned] = []

    def spawn(self, coro, *, name: str, log_stop: bool = False) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        task.add_done_callback(partial(_log_death, name))
        self._items.append(_Spawned(task=task, name=name, log_stop=log_stop))
        return task

    def supervise(
        self,
        factory: Factory,
        *,
        name: str,
        restart_seconds: float = 2.0,
        log_stop: bool = False,
    ) -> asyncio.Task:
        """Run ``factory`` forever; a crash is logged and the loop restarted."""
        restarted = _restart_forever(
            factory, name=name, restart_seconds=restart_seconds
        )
        return self.spawn(restarted, name=name, log_stop=log_stop)

    async def cancel_all(self) -> None:
        for item in self._items:
            item.task.cancel()
        await asyncio.gather(
            *(item.task for item in self._items), return_exceptions=True
        )
        for item in self._items:
            if item.log_stop:
                logger.info("%s stopped", item.name)
        self._items.clear()

