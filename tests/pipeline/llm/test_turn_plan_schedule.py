import json

import pytest

from vanessa.config.content import get_content
from vanessa.config.settings import settings
from vanessa.pipeline.decision.schedule_request import ScheduleRequest
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.llm.planner.schedule_parse import parse_schedule
from vanessa.pipeline.llm.planner.turn_planner import TurnPlanner

URL = "https://example.com/menu"


def _plan(schedule: object, *, should_reply: bool = False) -> TurnPlan:
    payload = {"should_reply": should_reply, "search_query": "", "skip": False}
    payload["schedule"] = schedule
    planner = TurnPlanner(use_llm=False)
    return planner._parse_llm_response("ванесса, ставь задачу", json.dumps(payload))


def test_add_cron_forces_reply_suggestion() -> None:
    plan = _plan({"action": "add", "cron": "0 13 * * 5", "at": "x", "text": f"Обеды {URL}"})
    assert plan.schedule == ScheduleRequest(action="add", cron="0 13 * * 5", text=f"Обеды {URL}")
    assert plan.should_reply is True


def test_add_once() -> None:
    plan = _plan({"action": "ADD", "at": "2026-10-22T10:00", "text": "Созвон"})
    assert plan.schedule == ScheduleRequest(action="add", at="2026-10-22T10:00", text="Созвон")


@pytest.mark.parametrize(
    "raw",
    [
        {"action": "add", "cron": "0 13 * * 5", "text": " "},
        {"action": "add", "text": "Обеды"},
        {"action": "pause"},
        "add",
        None,
    ],
)
def test_incomplete_or_unknown_is_dropped(raw: object) -> None:
    plan = _plan(raw)
    assert plan.schedule is None
    assert plan.should_reply is False


def test_list_and_cancel() -> None:
    assert _plan({"action": "list"}).schedule == ScheduleRequest(action="list")
    cancel = _plan({"action": "cancel", "target": " обеды "}).schedule
    assert cancel == ScheduleRequest(action="cancel", target="обеды")
    assert _plan({"action": "cancel"}).schedule == ScheduleRequest(action="cancel")


def test_text_clipped_to_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "schedule_text_max_chars", 5)
    request = parse_schedule({"schedule": {"action": "add", "cron": "0 9 * * *", "text": "abcdefgh"}})
    assert request.text == "abcde"


def test_disabled_skill_ignores_schedule(monkeypatch) -> None:
    monkeypatch.setattr(settings, "schedule_enabled", False)
    assert _plan({"action": "list"}).schedule is None


def test_trace_dict_includes_schedule() -> None:
    plan = TurnPlan(
        original="x", text="", skip_search=True, schedule=ScheduleRequest(action="list")
    )
    assert plan.to_trace_dict()["schedule"]["action"] == "list"
    assert TurnPlan(original="x", text="", skip_search=True).to_trace_dict()["schedule"] is None


def test_prompt_teaches_schedule_without_zone_names() -> None:
    prompt = get_content().rag.turn_planner_prompt
    assert "## schedule" in prompt
    assert "Current local time: {now}." in prompt
    assert '"schedule": null' in prompt
    assert "never write a time zone" in prompt
    assert '"cron": "0 13 * * 5"' in prompt
