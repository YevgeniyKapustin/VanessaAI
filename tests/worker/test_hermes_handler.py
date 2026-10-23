import asyncio
import time
from types import SimpleNamespace

import pytest

from services.worker.handlers.assembly import WorkerAssembly, with_hermes
from services.worker.hermes import HermesAskHandler, build_hermes_handler
from services.worker.hermes.payload import parse_hermes_ask
from tests.worker.hermes_fakes import (
    CHAT_ID,
    MESSAGE_ID,
    BlockingRunner,
    FakeBroker,
    FakeClient,
    FakeCompleter,
    ask_task,
    make_runner,
)
from vanessa.contracts.messages import TaskKind, TaskMessage

_FAST_SECONDS = 0.5
_TWO = 2
_DEFAULT_JOB_CAP = 8  # 2 running + 3 x 2 queued


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def test_handle_returns_fast_and_schedules() -> None:
    runner = BlockingRunner()
    handler = HermesAskHandler(runner, max_parallel=2)
    started = time.monotonic()
    await handler.handle(ask_task())
    assert time.monotonic() - started < _FAST_SECONDS
    await _settle()
    assert handler.job_count == 1
    assert runner.started[0].telegram_chat_id == CHAT_ID
    runner.release.set()
    await _settle()
    assert handler.job_count == 0


async def test_semaphore_bounds_parallel_runs_and_caps_queue() -> None:
    runner = BlockingRunner()
    handler = HermesAskHandler(runner, max_parallel=1, max_queued=1)
    for _ in range(3):
        await handler.handle(ask_task())
    await _settle()
    assert handler.job_count == _TWO  # one running, one queued, one dropped
    assert len(runner.started) == 1
    runner.release.set()
    await _settle()
    assert runner.peak == 1
    assert len(runner.started) == _TWO
    assert handler.job_count == 0


async def test_default_queue_is_three_per_slot() -> None:
    runner = BlockingRunner()
    handler = HermesAskHandler(runner, max_parallel=2)
    for _ in range(10):
        await handler.handle(ask_task())
    await _settle()
    assert handler.job_count == _DEFAULT_JOB_CAP
    assert runner.peak == _TWO
    await handler.aclose()


async def test_shutdown_cancels_jobs() -> None:
    runner = BlockingRunner()
    handler = HermesAskHandler(runner, max_parallel=1)
    await handler.handle(ask_task())
    await handler.handle(ask_task())
    await _settle()
    await handler.aclose()
    assert runner.cancelled == 1  # the queued one never started
    assert handler.job_count == 0


async def test_job_failure_is_contained() -> None:
    broker = FakeBroker(error=RuntimeError("redis down"))
    runner = make_runner(FakeClient(output="ok"), FakeCompleter("[answer]\nok"), broker)
    handler = HermesAskHandler(runner, max_parallel=1)
    await handler.handle(ask_task())
    await _settle()
    assert handler.job_count == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"question": "  "},
        {"telegram_chat_id": None},
        {"telegram_chat_id": "abc"},
        {"telegram_chat_id": True},
        {"channel": "vrchat"},
    ],
)
async def test_invalid_payload_is_ignored(overrides) -> None:
    runner = BlockingRunner()
    handler = HermesAskHandler(runner, max_parallel=1)
    await handler.handle(ask_task(**overrides))
    await _settle()
    assert handler.job_count == 0
    assert runner.started == []


def test_payload_parsing_and_idempotency_fallback() -> None:
    ask = parse_hermes_ask(ask_task(telegram_chat_id=str(CHAT_ID)))
    assert ask is not None
    assert ask.telegram_chat_id == CHAT_ID
    assert ask.telegram_message_id == MESSAGE_ID
    assert ask.idempotency_key == f"hermes:{CHAT_ID}:{MESSAGE_ID}"
    bare = TaskMessage(
        task=TaskKind.HERMES_ASK,
        payload={"question": "q", "telegram_chat_id": CHAT_ID},
    )
    parsed = parse_hermes_ask(bare)
    assert parsed is not None
    assert parsed.telegram_message_id is None
    assert parsed.idempotency_key == f"hermes:{CHAT_ID}:{bare.correlation_id}"


def _settings(*, enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        hermes_enabled=enabled,
        hermes_url="http://hermes:8642" if enabled else "",
        hermes_api_key="k",
        hermes_timeout_seconds=5.0,
        hermes_poll_seconds=5.0,
        hermes_max_wait_seconds=6000.0,
        hermes_file_max_bytes=262_144,
        hermes_max_parallel=2,
        knowledge_model="",
        planner_model="planner-model",
    )


def test_handler_not_registered_when_hermes_is_off() -> None:
    handler = build_hermes_handler(
        FakeBroker(), outbound_stream="o", settings=_settings(enabled=False)
    )
    assert handler is None
    assembly = with_hermes(WorkerAssembly(handlers={}), handler)
    assert TaskKind.HERMES_ASK not in assembly.handlers
    assert assembly.hermes is None


def test_handler_needs_broker_and_stream() -> None:
    settings = _settings(enabled=True)
    assert build_hermes_handler(None, outbound_stream="o", settings=settings) is None
    assert build_hermes_handler(FakeBroker(), outbound_stream="", settings=settings) is None


def test_handler_registered_when_hermes_is_on() -> None:
    handler = build_hermes_handler(
        FakeBroker(), outbound_stream="o", settings=_settings(enabled=True)
    )
    assert isinstance(handler, HermesAskHandler)
    assembly = with_hermes(WorkerAssembly(handlers={}), handler)
    assert assembly.handlers[TaskKind.HERMES_ASK] is handler
    assert assembly.hermes is handler
