from datetime import UTC, datetime
from unittest.mock import AsyncMock

from vanessa.config.content_schedule import get_schedule_content
from vanessa.core.reminders import Reminder
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.schedule_request import ScheduleRequest
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.stages.retrieve import RetrieveStage
from vanessa.pipeline.stages.retrieve_schedule import (
    run_schedule_step,
    schedule_request,
)

CHAT = -100500
LIST = ScheduleRequest(action="list")
POST = Reminder(
    id=1, chat_id=CHAT, text="Обеды", next_run_at=datetime(2030, 1, 4, 9, tzinfo=UTC)
)


def _ctx(
    schedule: ScheduleRequest | None = LIST, *, channel: str = "telegram"
) -> TurnPipelineContext:
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=CHAT if channel == "telegram" else None,
            message="ванесса, какие у тебя напоминалки?",
            sender_telegram_id=2,
            channel=channel,
        )
    )
    ctx.turn_plan = TurnPlan(original="x", text="", skip_search=True, schedule=schedule)
    return ctx


def _store(posts: list[Reminder] | None = None) -> AsyncMock:
    store = AsyncMock()
    store.list_for_chat.return_value = posts or []
    return store


async def test_list_sets_note() -> None:
    store = _store([POST])
    ctx = _ctx()
    await run_schedule_step(ctx, store)
    store.list_for_chat.assert_awaited_once_with(CHAT)
    assert "Обеды" in ctx.schedule_note


async def test_skips_without_store_request_or_telegram() -> None:
    store = _store()
    for ctx, used_store in (
        (_ctx(), None),
        (_ctx(None), store),
        (_ctx(channel="vrchat"), store),
    ):
        await run_schedule_step(ctx, used_store)
        assert ctx.schedule_note is None
    store.list_for_chat.assert_not_awaited()


async def test_store_error_fails_open() -> None:
    store = _store()
    store.list_for_chat.side_effect = RuntimeError("db down")
    ctx = _ctx()
    await run_schedule_step(ctx, store)
    assert ctx.schedule_note == get_schedule_content().error_note.strip()


def test_schedule_request_without_plan() -> None:
    ctx = _ctx()
    ctx.turn_plan = None
    assert schedule_request(ctx) is None


async def test_retrieve_stage_runs_schedule_step() -> None:
    store = _store()
    ctx = _ctx()
    assert await RetrieveStage(None, reminders=store).run(ctx) is True
    assert ctx.schedule_note == get_schedule_content().empty_note.strip()
