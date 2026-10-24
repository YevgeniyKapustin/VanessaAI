"""A lookup result posted lately stops a repeated lookup for a reaction."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from vanessa.config.settings import settings
from vanessa.core.hermes_answers import RecentAnswers
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.stages.retrieve import RetrieveStage
from vanessa.pipeline.stages.retrieve_hermes import run_hermes_step

CHAT_ID = -100500
QUESTION = "какой статус деплоя сервиса после релиза?"
REACTION = "ну и дела"


@pytest.fixture(autouse=True)
def _hermes_on(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_timeout_seconds", 0.05)


def _ctx(message: str, chat_id: int = CHAT_ID) -> TurnPipelineContext:
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=chat_id,
            message=message,
            sender_telegram_id=2,
            telegram_message_id=7,
        )
    )
    ctx.turn_plan = TurnPlan(
        original=message,
        text="",
        skip_search=True,
        ask_hermes=True,
        hermes_query=QUESTION,
    )
    return ctx


def _hermes() -> SimpleNamespace:
    return SimpleNamespace(is_online=AsyncMock(return_value=True))


def _answered() -> RecentAnswers:
    answers = RecentAnswers(window_seconds=600)
    answers.note(CHAT_ID, QUESTION)
    return answers


async def test_reaction_to_a_fresh_result_asks_nothing() -> None:
    hermes, dispatcher = _hermes(), MagicMock()
    ctx = _ctx(REACTION)
    await run_hermes_step(ctx, hermes, dispatcher, _answered())
    assert ctx.hermes_status == "answered"
    hermes.is_online.assert_not_awaited()
    dispatcher.submit.assert_not_called()


async def test_user_who_names_the_topic_asks_again() -> None:
    dispatcher = MagicMock()
    ctx = _ctx("проверь ещё раз статус деплоя")
    await run_hermes_step(ctx, _hermes(), dispatcher, _answered())
    assert ctx.hermes_status == "asked"
    dispatcher.submit.assert_called_once()


async def test_other_chat_asks() -> None:
    dispatcher = MagicMock()
    ctx = _ctx(REACTION, chat_id=CHAT_ID - 1)
    await run_hermes_step(ctx, _hermes(), dispatcher, _answered())
    assert ctx.hermes_status == "asked"


async def test_retrieve_stage_passes_the_answers() -> None:
    dispatcher = MagicMock()
    stage = RetrieveStage(
        None, hermes=_hermes(), dispatcher=dispatcher, hermes_answers=_answered()
    )
    ctx = _ctx(REACTION)
    assert await stage.run(ctx) is True
    assert ctx.hermes_status == "answered"
    dispatcher.submit.assert_not_called()
