"""Hermes asks: one job per question in a chat, and the real run time."""

import asyncio
import logging

import pytest

from services.worker.hermes import HermesAskHandler
from services.worker.hermes.dedupe import is_rephrase, question_stems
from services.worker.hermes.prompt import build_followup_user_prompt, format_duration
from tests.worker.hermes_fakes import (
    CHAT_ID,
    BlockingRunner,
    FakeBroker,
    FakeClient,
    FakeCompleter,
    ask_task,
    make_ask,
    make_runner,
)
from vanessa.config.content_hermes import get_hermes_content

FIRST = (
    "Открой в Grafana счётчики оплаты и покажи текущие значения: счётчик "
    "успешных платежей Alpha, счётчик Beta и счётчик возвратов. Ожидаемо: "
    "Alpha вырос на 1"
)
REPHRASE = (
    "Проверь в Grafana счётчики оплаты: вырос ли счётчик успешных платежей "
    "Alpha на 1, остались ли прежними счётчик Beta и счётчик возвратов?"
)
OTHER = "Какие задачи висят в текущем спринте рабочего проекта?"
_TWO = 2


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


def _rephrase(new: str, old: str) -> bool:
    return is_rephrase(question_stems(new), question_stems(old))


def test_rephrase_matches_and_other_question_does_not() -> None:
    assert _rephrase(REPHRASE, FIRST)
    assert not _rephrase(OTHER, FIRST)
    # Short questions share too few stems to count as one lookup.
    assert not _rephrase("что в Plane по VAN-12?", "что в Plane по VAN-13?")


async def test_rephrase_in_same_chat_is_merged_while_open(caplog) -> None:
    runner = BlockingRunner()
    handler = HermesAskHandler(runner, max_parallel=2)
    with caplog.at_level(logging.INFO):
        await handler.handle(ask_task(question=FIRST))
        await handler.handle(ask_task(question=REPHRASE, telegram_message_id=43))
        await _settle()
    assert len(runner.started) == 1
    assert "hermes_ask_merged" in caplog.text
    runner.release.set()
    await _settle()
    # The first job is done: the same question starts a new job.
    runner.release.clear()
    await handler.handle(ask_task(question=REPHRASE))
    await _settle()
    assert len(runner.started) == _TWO
    await handler.aclose()


@pytest.mark.parametrize(
    "overrides",
    [{"question": OTHER}, {"question": REPHRASE, "telegram_chat_id": CHAT_ID - 1}],
)
async def test_other_question_or_other_chat_starts_own_job(overrides) -> None:
    runner = BlockingRunner()
    handler = HermesAskHandler(runner, max_parallel=2)
    await handler.handle(ask_task(question=FIRST))
    await handler.handle(ask_task(**overrides))
    await _settle()
    assert len(runner.started) == _TWO
    await handler.aclose()


def test_format_duration() -> None:
    assert format_duration(0.2) == "1 second"
    assert format_duration(16.4) == "16 seconds"
    assert format_duration(185) == "3 minutes"


def test_prompt_carries_real_run_time_before_task() -> None:
    prompts = get_hermes_content()
    prompt = build_followup_user_prompt(
        make_ask(), "answer", prompts, elapsed_seconds=16
    )
    assert "took 16 seconds" in prompt
    assert prompt.index("took 16 seconds") < prompt.index("<!-- Task -->")
    assert "{duration}" not in build_followup_user_prompt(make_ask(), "a", prompts)


async def test_runner_passes_elapsed_time_to_prompt() -> None:
    completer = FakeCompleter("[answer]\nГотово")
    runner = make_runner(FakeClient(output="data"), completer, FakeBroker())
    await runner.run(make_ask())
    user = completer.calls[0]["messages"][-1]["content"]
    assert "This lookup ran once and took" in user
