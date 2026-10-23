import asyncio
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import AsyncMock

from services.worker.app import WorkerApp
from services.worker.main import main
from vanessa.contracts.messages import TaskKind

_LOOP_COUNT = 2


class _CloseBroker:
    def __init__(self) -> None:
        self.closed = 0

    def dedup_guard(self):
        return None

    def janitor(self, *_args):
        return _Collector()

    async def close(self) -> None:
        self.closed += 1


class _Collector:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    async def run_forever(self) -> None:
        await asyncio.Event().wait()


class _Assembly:
    def __init__(self) -> None:
        self.handlers = {TaskKind.SWEEP: SimpleNamespace(handle=AsyncMock())}
        self.sweep = None
        self.portrait = None
        self.hermes = None


async def _cancel_forever(self) -> None:
    del self
    raise asyncio.CancelledError


async def test_worker_run_forever_with_loops() -> None:
    started: list[str] = []

    class Loop:
        async def run_forever(self) -> None:
            started.append("loop")
            await asyncio.Event().wait()

    class Broker:
        async def consume_forever(self, *args, **kwargs) -> None:
            del args, kwargs
            started.append("consume")
            await asyncio.Event().wait()

    app = WorkerApp(
        Broker(),
        {},
        tasks_stream="tasks",
        group="g",
        consumer="c",
        sweep_worker=Loop(),
        portrait_worker=Loop(),
    )
    task = asyncio.create_task(app.run_forever())
    await asyncio.sleep(0.02)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert "consume" in started
    assert started.count("loop") == _LOOP_COUNT


async def test_worker_handle_unexpected_kind() -> None:
    app = WorkerApp(SimpleNamespace(), {}, tasks_stream="t", group="g", consumer="c")
    await app._handle(
        SimpleNamespace(message=SimpleNamespace(message_kind=lambda: "x"), stream="t")
    )


def _patch_worker_main(monkeypatch, assembly=None) -> _CloseBroker:
    broker = _CloseBroker()
    monkeypatch.setattr("services.worker.main.configure_logging", lambda _n: None)
    monkeypatch.setattr(
        "services.worker.main.start_metrics_http_server", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        "services.worker.main.BrokerStreams.from_settings",
        lambda _s: SimpleNamespace(turns="t", tasks="k", outbound="o"),
    )
    monkeypatch.setattr(
        "services.worker.main.RedisStreamBroker",
        lambda *_a, **_k: broker,
    )
    monkeypatch.setattr("services.worker.main.BrokerMetricsCollector", _Collector)
    monkeypatch.setattr(
        "services.worker.main.build_worker_handlers",
        AsyncMock(return_value=assembly or _Assembly()),
    )
    monkeypatch.setattr("services.worker.main.WorkerApp.run_forever", _cancel_forever)
    return broker


async def test_worker_main_runs_until_cancelled(monkeypatch) -> None:
    broker = _patch_worker_main(monkeypatch)
    with suppress(asyncio.CancelledError):
        await main()
    assert broker.closed == 1


async def test_worker_main_closes_hermes_jobs(monkeypatch) -> None:
    assembly = _Assembly()
    assembly.hermes = SimpleNamespace(aclose=AsyncMock())
    broker = _patch_worker_main(monkeypatch, assembly)
    with suppress(asyncio.CancelledError):
        await main()
    assembly.hermes.aclose.assert_awaited_once()
    assert broker.closed == 1
