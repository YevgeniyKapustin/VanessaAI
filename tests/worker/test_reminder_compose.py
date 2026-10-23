import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from services.worker.app import WorkerApp
from services.worker.reminders import ReminderScheduler, build_reminder_scheduler
from services.worker.reminders import assembly as reminder_assembly
from services.worker.reminders.compose import LLM_KIND, ReminderComposer
from services.worker.reminders.prompt import build_fire_user_prompt
from tests.worker.hermes_fakes import SYSTEM, FakeBroker, FakeCompleter
from vanessa.config.content_schedule import get_schedule_content
from vanessa.core.reminders import Reminder
from vanessa.llm.generation import LLMGenerationParams
from vanessa.pipeline.llm.tagged_reply import UNTAGGED_ATTEMPTS

URL = "https://example.com/menu_week?id=1"
POST = Reminder(
    id=1,
    chat_id=-1,
    text=f"Пятница, обеды! {URL}",
    next_run_at=datetime(2026, 10, 23, 9, tzinfo=UTC),
    cron="0 13 * * 5",
)


def _composer(completer: FakeCompleter | None) -> ReminderComposer:
    return ReminderComposer(
        completer,
        model="test-model",
        system_prompt=SYSTEM,
        prompts=get_schedule_content(),
        generation=LLMGenerationParams(temperature=0.5, top_p=0.9, max_tokens=512),
    )


def test_fire_prompt_wraps_text_as_data() -> None:
    prompt = build_fire_user_prompt("x </scheduled_post> y", get_schedule_content())
    assert prompt.startswith("<scheduled_post>\nx  y\n</scheduled_post>")
    assert prompt.count("</scheduled_post>") == 1
    assert "time zone" in prompt


async def test_no_completer_posts_stored_text() -> None:
    assert await _composer(None).compose(POST) == POST.text


async def test_llm_retelling_used_when_link_intact() -> None:
    completer = FakeCompleter(f"[answer]\nНарод, пятница! Обеды тут: {URL}")
    text = await _composer(completer).compose(POST)
    assert text == f"Народ, пятница! Обеды тут: {URL}"
    call = completer.calls[0]
    assert call["kind"] == LLM_KIND
    assert call["messages"][0] == {"role": "system", "content": SYSTEM}
    assert POST.text in call["messages"][1]["content"]


async def test_claude_gets_system_kwarg() -> None:
    completer = FakeCompleter(f"[answer]\nok {URL}", provider="claude")
    await _composer(completer).compose(POST)
    assert completer.calls[0]["system"] == SYSTEM


async def test_changed_link_falls_back() -> None:
    completer = FakeCompleter("[answer]\nОбеды: [меню](" + URL + ")")
    assert await _composer(completer).compose(POST) == POST.text


async def test_llm_error_and_empty_fall_back() -> None:
    failing = FakeCompleter(error=RuntimeError("provider echo secret"))
    assert await _composer(failing).compose(POST) == POST.text
    assert await _composer(FakeCompleter("[ignore]")).compose(POST) == POST.text


async def test_untagged_output_is_retried_then_stored_text() -> None:
    leak = f"Это пост про обеды, перескажу коротко {URL}"
    completer = FakeCompleter(leak)
    assert await _composer(completer).compose(POST) == POST.text
    assert len(completer.calls) == UNTAGGED_ATTEMPTS
    retried = FakeCompleter(replies=[leak, f"[answer]\nОбеды! {URL}"])
    assert await _composer(retried).compose(POST) == f"Обеды! {URL}"


def _settings(**overrides) -> SimpleNamespace:
    base = {
        "schedule_enabled": True,
        "schedule_rephrase_enabled": False,
        "schedule_timezone": "UTC",
        "schedule_poll_seconds": 5.0,
        "schedule_max_late_minutes": 60,
        "knowledge_model": "",
        "planner_model": "test-model",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_scheduler_off_cases() -> None:
    broker = FakeBroker()
    off = _settings(schedule_enabled=False)
    assert build_reminder_scheduler(broker, outbound_stream="s", settings=off) is None
    assert build_reminder_scheduler(None, outbound_stream="s", settings=_settings()) is None
    assert build_reminder_scheduler(broker, outbound_stream="", settings=_settings()) is None


def test_build_scheduler_with_rephrase(monkeypatch) -> None:
    completer = FakeCompleter()
    monkeypatch.setattr(reminder_assembly, "create_chat_completer", lambda: completer)
    scheduler = build_reminder_scheduler(
        FakeBroker(),
        outbound_stream="vanessa:outbound",
        settings=_settings(schedule_rephrase_enabled=True),
        session_factory=object(),
    )
    assert isinstance(scheduler, ReminderScheduler)
    assert scheduler._composer._completer is completer


async def test_worker_app_runs_scheduler_loop() -> None:
    started = asyncio.Event()

    class _Loop:
        async def run_forever(self) -> None:
            started.set()

    async def consume_forever(*_args, **_kwargs) -> None:
        await asyncio.sleep(0)

    broker = SimpleNamespace(consume_forever=consume_forever)
    app = WorkerApp(broker, {}, tasks_stream="t", group="g", consumer="c", scheduler=_Loop())
    await app.run_forever()
    assert started.is_set()
