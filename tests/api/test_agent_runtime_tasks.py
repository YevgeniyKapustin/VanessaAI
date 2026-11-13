import asyncio
import inspect

from services.agent.runtime.tasks import TaskSet


def test_supervise_takes_the_same_keywords_as_spawn() -> None:
    spawn_keys = set(inspect.signature(TaskSet.spawn).parameters)
    supervise_keys = set(inspect.signature(TaskSet.supervise).parameters)
    assert spawn_keys - {"self", "coro"} <= supervise_keys


async def test_supervise_restarts_a_crashed_loop() -> None:
    calls: list[int] = []

    async def _factory() -> None:
        calls.append(1)
        raise RuntimeError("loop died")

    tasks = TaskSet()
    tasks.supervise(_factory, name="flaky", restart_seconds=0.0, log_stop=True)
    await asyncio.sleep(0.05)
    await tasks.cancel_all()
    assert len(calls) >= 2


async def test_supervise_restarts_a_loop_that_returns() -> None:
    calls: list[int] = []

    async def _factory() -> None:
        calls.append(1)

    tasks = TaskSet()
    tasks.supervise(_factory, name="returning", restart_seconds=0.0)
    await asyncio.sleep(0.05)
    await tasks.cancel_all()
    assert len(calls) >= 2


class _RecordingLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def error(self, message, *args, **kwargs) -> None:
        del kwargs
        self.messages.append(message % args if args else message)


async def test_dead_task_is_logged(monkeypatch) -> None:
    async def _boom() -> None:
        raise RuntimeError("boom")

    recorder = _RecordingLogger()
    monkeypatch.setattr("services.agent.runtime.tasks.logger", recorder)
    tasks = TaskSet()
    tasks.spawn(_boom(), name="boom")
    await asyncio.sleep(0.01)
    await tasks.cancel_all()
    assert any("boom died" in message for message in recorder.messages)


async def test_spawned_task_survives_cancel_all() -> None:
    async def _idle() -> None:
        await asyncio.Event().wait()

    tasks = TaskSet()
    task = tasks.spawn(_idle(), name="idle", log_stop=True)
    await asyncio.sleep(0)
    await tasks.cancel_all()
    assert task.cancelled() is True
