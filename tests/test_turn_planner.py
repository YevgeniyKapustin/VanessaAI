import pytest

from app.llm.turn_planner import TurnPlanner


async def test_turn_planner_parse_should_reply():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "что думаешь про тик така",
        '{"should_reply": false, "search_query": "тик так", "skip": false, '
        '"humor_ok": false, "humor_query": ""}',
    )

    assert result.should_reply is False
    assert result.text == "тик так"


@pytest.mark.asyncio
async def test_turn_planner_parse_humor_fields():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "ну ладно поработаю",
        '{"search_query": "работа", "skip": false, '
        '"humor_ok": true, "humor_query": "личь работа"}',
    )

    assert result.text == "работа"
    assert result.humor_ok is True
    assert result.humor_query == "личь работа"


@pytest.mark.asyncio
async def test_turn_planner_humor_ok_without_query_disabled():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "test",
        '{"search_query": "x", "skip": false, "humor_ok": true, "humor_query": ""}',
    )

    assert result.humor_ok is False
    assert result.humor_query == ""


@pytest.mark.asyncio
async def test_turn_planner_strips_markdown_fence():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "крабер",
        '```json\n{"search_query": "Крабер", "skip": false, '
        '"humor_ok": true, "humor_query": "крабер подкол"}\n```',
    )

    assert result.text == "Крабер"
    assert result.humor_ok is True
    assert result.humor_query == "крабер подкол"
