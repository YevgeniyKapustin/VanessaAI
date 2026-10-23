import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from vanessa.config.settings import settings
from vanessa.contracts.messages import TaskKind
from vanessa.core.request_context import request_id_var
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.stages.retrieve import RetrieveStage
from vanessa.pipeline.stages.retrieve_hermes import run_hermes_step

_CHAT_ID = -100500
_MESSAGE_ID = 77
_QUESTION = "Какой статус пайплайна у MR 42 в vanessa-ai?"


@pytest.fixture(autouse=True)
def _hermes_on(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_timeout_seconds", 0.05)


def _ctx(
    *,
    ask: bool = True,
    channel: str = "telegram",
    message_id: int | None = _MESSAGE_ID,
) -> TurnPipelineContext:
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=_CHAT_ID if channel == "telegram" else None,
            message="ванесса, что с пайплайном в MR 42?",
            sender_telegram_id=2,
            channel=channel,
            telegram_message_id=message_id,
            correlation_id="corr-1",
        )
    )
    ctx.turn_plan = TurnPlan(
        original="x",
        text="",
        skip_search=True,
        ask_hermes=ask,
        hermes_query=_QUESTION if ask else "",
    )
    return ctx


def _hermes(*, online: bool = True) -> SimpleNamespace:
    return SimpleNamespace(is_online=AsyncMock(return_value=online))


async def test_disabled_does_nothing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hermes_enabled", False)
    hermes, dispatcher = _hermes(), MagicMock()
    ctx = _ctx()
    await run_hermes_step(ctx, hermes, dispatcher)
    assert ctx.hermes_status is None
    hermes.is_online.assert_not_awaited()
    dispatcher.submit.assert_not_called()


@pytest.mark.parametrize(
    ("hermes", "dispatcher"),
    [(None, MagicMock()), (_hermes(), None)],
)
async def test_missing_client_or_dispatcher_skips(hermes, dispatcher) -> None:
    ctx = _ctx()
    await run_hermes_step(ctx, hermes, dispatcher)
    assert ctx.hermes_status is None


async def test_not_flagged_skips() -> None:
    hermes, dispatcher = _hermes(), MagicMock()
    ctx = _ctx(ask=False)
    await run_hermes_step(ctx, hermes, dispatcher)
    assert ctx.hermes_status is None
    hermes.is_online.assert_not_awaited()


async def test_non_telegram_skips() -> None:
    hermes, dispatcher = _hermes(), MagicMock()
    ctx = _ctx(channel="vrchat")
    await run_hermes_step(ctx, hermes, dispatcher)
    assert ctx.hermes_status is None
    hermes.is_online.assert_not_awaited()
    dispatcher.submit.assert_not_called()


async def test_offline_marks_status_without_dispatch() -> None:
    dispatcher = MagicMock()
    ctx = _ctx()
    await run_hermes_step(ctx, _hermes(online=False), dispatcher)
    assert ctx.hermes_status == "offline"
    dispatcher.submit.assert_not_called()


async def test_health_timeout_is_offline() -> None:
    async def _hang() -> bool:
        await asyncio.sleep(1)
        return True

    dispatcher = MagicMock()
    ctx = _ctx()
    await run_hermes_step(ctx, SimpleNamespace(is_online=_hang), dispatcher)
    assert ctx.hermes_status == "offline"
    dispatcher.submit.assert_not_called()


async def test_online_dispatches_exact_task() -> None:
    dispatcher = MagicMock()
    ctx = _ctx()
    await run_hermes_step(ctx, _hermes(), dispatcher)
    assert ctx.hermes_status == "asked"
    dispatcher.submit.assert_called_once_with(
        TaskKind.HERMES_ASK,
        {
            "question": _QUESTION,
            "channel": "telegram",
            "telegram_chat_id": _CHAT_ID,
            "telegram_message_id": _MESSAGE_ID,
            "user_message": "ванесса, что с пайплайном в MR 42?",
        },
        dedup_key=f"hermes:{_CHAT_ID}:{_MESSAGE_ID}",
    )


async def test_dedup_falls_back_to_correlation_id() -> None:
    dispatcher = MagicMock()
    await run_hermes_step(_ctx(message_id=None), _hermes(), dispatcher)
    payload = dispatcher.submit.call_args.args[1]
    assert payload["telegram_message_id"] is None
    assert dispatcher.submit.call_args.kwargs["dedup_key"] == (
        f"hermes:{_CHAT_ID}:corr-1"
    )


async def test_dedup_falls_back_to_request_id() -> None:
    dispatcher = MagicMock()
    ctx = _ctx(message_id=None)
    ctx.turn = ChatTurnInput(
        telegram_chat_id=_CHAT_ID, message="m", sender_telegram_id=2
    )
    token = request_id_var.set("req-9")
    try:
        await run_hermes_step(ctx, _hermes(), dispatcher)
    finally:
        request_id_var.reset(token)
    assert dispatcher.submit.call_args.kwargs["dedup_key"] == f"hermes:{_CHAT_ID}:req-9"


async def test_health_error_is_offline() -> None:
    hermes = SimpleNamespace(is_online=AsyncMock(side_effect=RuntimeError("down")))
    dispatcher = MagicMock()
    ctx = _ctx()
    await run_hermes_step(ctx, hermes, dispatcher)
    assert ctx.hermes_status == "offline"
    dispatcher.submit.assert_not_called()


async def test_dispatch_error_is_offline() -> None:
    dispatcher = MagicMock()
    dispatcher.submit.side_effect = RuntimeError("broker down")
    ctx = _ctx()
    await run_hermes_step(ctx, _hermes(), dispatcher)
    assert ctx.hermes_status == "offline"


async def test_retrieve_stage_runs_hermes_step() -> None:
    dispatcher = MagicMock()
    stage = RetrieveStage(None, hermes=_hermes(), dispatcher=dispatcher)
    ctx = _ctx()
    assert await stage.run(ctx) is True
    assert ctx.hermes_status == "asked"
    dispatcher.submit.assert_called_once()
