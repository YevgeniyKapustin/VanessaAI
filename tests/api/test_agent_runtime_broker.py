from types import SimpleNamespace
from unittest.mock import AsyncMock

from services.agent.runtime.broker import BrokerRuntime, _start_outbox


class _Tasks:
    def __init__(self) -> None:
        self.spawned: list[str] = []

    def spawn(self, coro, *, name: str, log_stop: bool = False) -> None:
        del log_stop
        self.spawned.append(name)
        coro.close()

    async def cancel_all(self) -> None:
        self.spawned.append("cancel")


class _HealthyBroker:
    def __init__(self) -> None:
        self.closed = False

    def ensure_client(self):
        return SimpleNamespace(ping=AsyncMock(), dedup_guard=lambda: None)

    async def close(self) -> None:
        self.closed = True


class _DownBroker:
    def ensure_client(self):
        return SimpleNamespace(ping=AsyncMock(side_effect=RuntimeError("down")))


async def test_broker_runtime_start_stop(monkeypatch) -> None:
    tasks = _Tasks()
    broker = _HealthyBroker()
    container = SimpleNamespace(graph=SimpleNamespace(broker=broker, hermes_answers=None))
    monkeypatch.setattr("services.agent.runtime.broker.TaskSet", lambda: tasks)
    monkeypatch.setattr("services.agent.runtime.broker.settings.outbox_enabled", True)
    runtime = BrokerRuntime(container)
    await runtime.start()
    await runtime.stop()
    assert "broker_turn_worker" in tasks.spawned
    assert "outbox_relay" in tasks.spawned
    assert "broker_metrics" in tasks.spawned
    assert broker.closed is True


async def test_broker_runtime_ping_failure() -> None:
    container = SimpleNamespace(graph=SimpleNamespace(broker=_DownBroker()))
    runtime = BrokerRuntime(container)
    try:
        await runtime.start()
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass


def test_start_outbox_disabled(monkeypatch) -> None:
    monkeypatch.setattr("services.agent.runtime.broker.settings.outbox_enabled", False)
    tasks = SimpleNamespace(spawn=lambda *_a, **_k: None)
    _start_outbox(tasks, SimpleNamespace())
