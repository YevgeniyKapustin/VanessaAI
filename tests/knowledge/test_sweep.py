import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from types import SimpleNamespace

from vanessa.core.messages import StoredMessage
from vanessa.knowledge.memory.sweep import SweepAnalyzer, SweepWorker, chunk_windows
from vanessa.knowledge.schema import MemoryPlan, VaultNote

_WINDOW = 2
_CURSOR = 3


def test_chunk_windows_edges() -> None:
    assert chunk_windows([], 10, 2) == []
    assert chunk_windows([1, 2, 3], 0, 1) == []
    windows = chunk_windows(list(range(5)), 3, 1)
    assert windows[0] == [0, 1, 2]
    assert len(windows) >= _WINDOW


class _Vault:
    def __init__(self, *, configured: bool = True) -> None:
        self.is_configured = configured
        self.state = {"last_message_id": "bad"}
        self.notes: dict[str, VaultNote] = {}

    async def read_state(self) -> dict:
        return self.state

    async def write_state(self, data: dict) -> None:
        self.state = data

    async def read_note(self, relative_path: str) -> VaultNote | None:
        return self.notes.get(relative_path)

    async def write_note(self, relative_path: str, meta: dict, body: str, **_k) -> str:
        self.notes[relative_path] = VaultNote(relative_path, meta, body)
        return relative_path

    async def list_notes(self, folder: str, **_k):
        del folder
        return list(self.notes.values())


class _Planner:
    def __init__(self, *, error: bool = False) -> None:
        self.error = error

    async def decide(self, transcript: str) -> MemoryPlan:
        del transcript
        if self.error:
            raise RuntimeError("plan")
        return MemoryPlan(updates=({"type": "quote", "person": "Ada", "quote": "hi"},))


class _Writer:
    def __init__(self, *, error: bool = False) -> None:
        self.error = error
        self.calls = 0

    async def apply(self, plan, **kwargs) -> int:
        del plan, kwargs
        self.calls += 1
        if self.error:
            raise RuntimeError("apply")
        return 1


class _Repo:
    def __init__(self, messages: list[StoredMessage]) -> None:
        self.messages = messages

    async def get_newer_than(self, cursor: int, limit: int = 200) -> list[StoredMessage]:
        del limit
        return [message for message in self.messages if message.id > cursor]


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a) -> bool:
        return False


class _FailingSession:
    async def __aenter__(self):
        raise RuntimeError("db")

    async def __aexit__(self, *_a) -> bool:
        return False


def _msg(msg_id: int) -> StoredMessage:
    return StoredMessage(
        id=msg_id,
        role="user",
        content="hello from the chat window",
        sender_telegram_id=1,
        sender_name="Ada",
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


async def _cancel_sleep(_seconds) -> None:
    raise asyncio.CancelledError


async def test_sweep_unconfigured_and_below_interval() -> None:
    analyzer = SweepAnalyzer(
        _Vault(configured=False), _Planner(), _Writer(), interval_messages=2
    )
    assert await analyzer.run(_Repo([_msg(1)])) == 0
    analyzer = SweepAnalyzer(_Vault(), _Planner(), _Writer(), interval_messages=50)
    assert await analyzer.run(_Repo([_msg(1)])) == 0


async def test_sweep_processes_windows_and_saves_cursor() -> None:
    vault = _Vault()
    writer = _Writer()
    analyzer = SweepAnalyzer(
        vault,
        _Planner(),
        writer,
        interval_messages=2,
        batch_size=10,
        window_size=2,
        window_overlap=0,
    )
    processed = await analyzer.run(_Repo([_msg(1), _msg(2), _msg(3)]))
    assert processed >= _WINDOW
    assert vault.state["last_message_id"] == _CURSOR
    assert writer.calls >= 1


async def test_sweep_swallows_plan_apply_metrics_compaction() -> None:
    vault = _Vault()
    vault.state = {"last_message_id": 0}

    class Metrics:
        async def run(self, _repo, **kwargs) -> int:
            del kwargs
            raise RuntimeError("metrics")

    analyzer = SweepAnalyzer(
        vault,
        _Planner(error=True),
        _Writer(error=True),
        interval_messages=1,
        window_size=2,
        metrics=Metrics(),
    )
    processed = await analyzer.run(_Repo([_msg(1)]))
    assert processed == 0


class _OneCycleSweep:
    def __init__(self) -> None:
        self.n = 0

    async def run(self, repo) -> int:
        del repo
        self.n += 1
        return 1


async def test_sweep_worker_one_cycle(monkeypatch) -> None:
    sweep = _OneCycleSweep()
    monkeypatch.setattr("vanessa.knowledge.memory.sweep.asyncio.sleep", _cancel_sleep)
    monkeypatch.setattr(
        "vanessa.knowledge.memory.sweep.MessageRepository",
        lambda _session: SimpleNamespace(),
    )
    worker = SweepWorker(sweep, _Session, poll_seconds=0)
    with suppress(asyncio.CancelledError):
        await worker.run_forever()
    assert sweep.n == 1


async def test_sweep_worker_swallows_cycle_error(monkeypatch) -> None:
    monkeypatch.setattr("vanessa.knowledge.memory.sweep.asyncio.sleep", _cancel_sleep)
    worker = SweepWorker(SimpleNamespace(), _FailingSession, poll_seconds=0)
    with suppress(asyncio.CancelledError):
        await worker.run_forever()
