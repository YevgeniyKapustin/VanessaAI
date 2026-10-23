import json
import re

from vanessa.config.content import get_content
from vanessa.config.settings import settings
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.llm.planner.turn_planner import TurnPlanner

_BASE = '"should_reply": true, "search_query": "", "skip": false'


def _parse(extra: str) -> TurnPlan:
    planner = TurnPlanner(use_llm=False)
    return planner._parse_llm_response("что с MR 42", "{" + _BASE + extra + "}")


def test_parses_hermes_fields() -> None:
    plan = _parse(', "ask_hermes": true, "hermes_query": " Статус MR 42? "')
    assert plan.ask_hermes is True
    assert plan.hermes_query == "Статус MR 42?"


def test_hermes_off_by_default() -> None:
    plan = _parse("")
    assert plan.ask_hermes is False
    assert plan.hermes_query == ""


def test_ask_hermes_dropped_without_query() -> None:
    plan = _parse(', "ask_hermes": true, "hermes_query": "  "')
    assert plan.ask_hermes is False
    assert plan.hermes_query == ""


def test_query_dropped_without_flag() -> None:
    plan = _parse(', "ask_hermes": false, "hermes_query": "Статус MR 42?"')
    assert plan.ask_hermes is False
    assert plan.hermes_query == ""


def test_hermes_query_clipped_to_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hermes_query_max_chars", 5)
    plan = _parse(', "ask_hermes": true, "hermes_query": "abcdefghij"')
    assert plan.hermes_query == "abcde"


def test_skip_plan_never_asks_hermes() -> None:
    planner = TurnPlanner(use_llm=False)
    plan = planner._parse_llm_response(
        "ок",
        '{"should_reply": false, "skip": true, "ask_hermes": true, '
        '"hermes_query": "x", "reason": "пустая фраза"}',
    )
    assert plan.ask_hermes is False


def test_trace_dict_includes_hermes() -> None:
    plan = TurnPlan(
        original="x",
        text="",
        skip_search=True,
        ask_hermes=True,
        hermes_query="Статус MR 42?",
    )
    data = plan.to_trace_dict()
    assert data["ask_hermes"] is True
    assert data["hermes_query"] == "Статус MR 42?"


def test_prompt_teaches_hermes() -> None:
    prompt = get_content().rag.turn_planner_prompt
    assert '"ask_hermes": false' in prompt
    assert '"hermes_query": ""' in prompt
    assert "## ask_hermes / hermes_query" in prompt
    assert '"ask_hermes": true' in prompt


def _schema_keys(prompt: str) -> set[str]:
    schema = prompt.split("## Output format", 1)[1].split("}}", 1)[0]
    return set(re.findall(r'^\s+"(\w+)":', schema, flags=re.MULTILINE))


def test_every_planner_example_lists_every_field() -> None:
    prompt = get_content().rag.turn_planner_prompt
    keys = _schema_keys(prompt)
    assert {"ask_hermes", "hermes_query"} <= keys
    examples = re.findall(r"→ (\{\{.*\}\})", prompt)
    assert examples
    for example in examples:
        data = json.loads(example.replace("{{", "{").replace("}}", "}"))
        assert set(data) == keys, example
