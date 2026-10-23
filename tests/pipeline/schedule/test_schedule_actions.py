from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

from vanessa.core.reminders import NewReminder, Reminder
from vanessa.pipeline.decision.schedule_request import ScheduleRequest
from vanessa.pipeline.schedule.actions import ScheduleCall, apply_schedule
from vanessa.pipeline.schedule.timing import SchedulePolicy

CHAT = -100500
URL = "https://example.com/menu"
NOW = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)
POLICY = SchedulePolicy(tz=timezone(timedelta(hours=4)), max_per_chat=2)


class FakeStore:
    def __init__(self) -> None:
        self.rows: list[Reminder] = []

    async def add(self, new: NewReminder) -> Reminder:
        reminder = Reminder(id=len(self.rows) + 1, **vars_of(new))
        self.rows.append(reminder)
        return reminder

    async def list_for_chat(self, chat_id: int) -> list[Reminder]:
        return [r for r in self.rows if r.chat_id == chat_id]

    async def delete(self, chat_id: int, ids: list[int]) -> int:
        before = len(self.rows)
        self.rows = [r for r in self.rows if not (r.chat_id == chat_id and r.id in ids)]
        return before - len(self.rows)


def vars_of(new: NewReminder) -> dict:
    return {field: getattr(new, field) for field in new.__slots__}


def _call(request: ScheduleRequest, source: str = "") -> ScheduleCall:
    return ScheduleCall(
        request=request,
        chat_id=CHAT,
        source_text=source,
        now_utc=NOW,
        policy=POLICY,
        sender_id=7,
    )


ADD = ScheduleRequest(action="add", cron="0 13 * * 5", text="Пятница, обеды!")


async def test_add_stores_post_and_keeps_link() -> None:
    store = FakeStore()
    outcome = await apply_schedule(_call(ADD, f"кидай обеды {URL}"), store)
    assert outcome.status == "added"
    (row,) = store.rows
    assert row.text == f"Пятница, обеды!\n{URL}"
    assert row.next_run_at == datetime(2026, 10, 23, 9, tzinfo=UTC)
    assert (row.cron, row.created_by, row.chat_id) == ("0 13 * * 5", 7, CHAT)


async def test_add_rejects_frequent_cron() -> None:
    store = FakeStore()
    outcome = await apply_schedule(_call(replace(ADD, cron="* * * * *")), store)
    assert (outcome.status, outcome.detail) == ("rejected", "too_frequent")
    assert store.rows == []


async def test_add_respects_chat_cap() -> None:
    store = FakeStore()
    for _ in range(POLICY.max_per_chat):
        await apply_schedule(_call(ADD), store)
    outcome = await apply_schedule(_call(ADD), store)
    assert (outcome.status, outcome.detail) == ("rejected", "limit")
    assert len(store.rows) == POLICY.max_per_chat


async def test_list_empty_and_listed() -> None:
    store = FakeStore()
    listing = ScheduleRequest(action="list")
    assert (await apply_schedule(_call(listing), store)).status == "empty"
    await apply_schedule(_call(ADD), store)
    outcome = await apply_schedule(_call(listing), store)
    assert outcome.status == "listed"
    assert len(outcome.reminders) == 1


async def test_cancel_paths() -> None:
    store = FakeStore()
    cancel = ScheduleRequest(action="cancel", target="")
    assert (await apply_schedule(_call(cancel), store)).status == "empty"
    await apply_schedule(_call(ADD), store)
    await apply_schedule(_call(replace(ADD, text="Созвон в десять")), store)
    assert (await apply_schedule(_call(cancel), store)).status == "ambiguous"
    missing = replace(cancel, target="кино")
    assert (await apply_schedule(_call(missing), store)).status == "not_found"
    outcome = await apply_schedule(_call(replace(cancel, target="обеды")), store)
    assert outcome.status == "cancelled"
    assert [r.text for r in store.rows] == ["Созвон в десять"]


async def test_unknown_action_rejected() -> None:
    outcome = await apply_schedule(_call(ScheduleRequest(action="nope")), FakeStore())
    assert (outcome.status, outcome.detail) == ("rejected", "bad_action")
