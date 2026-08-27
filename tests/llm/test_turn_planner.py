import pytest

from app.llm.planner.turn_planner import TurnPlanner


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
async def test_turn_planner_parse_deep_search():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "сравни меш и текстуры",
        '{"should_reply": true, "search_query": "меш текстуры", "skip": false, '
        '"humor_ok": false, "humor_query": "", "deep_search": true}',
    )

    assert result.deep_search is True
    assert result.text == "меш текстуры"


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


@pytest.mark.asyncio
async def test_turn_planner_parse_knowledge_fields():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "что там у Лича",
        '{"search_query": "личь", "skip": false, "humor_ok": false, '
        '"humor_query": "", "knowledge_indexes": ["people"], '
        '"knowledge_query": "личь"}',
    )

    assert result.knowledge_indexes == ("people",)
    assert result.knowledge_query == "личь"


@pytest.mark.asyncio
async def test_turn_planner_knowledge_defaults_empty():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "ок",
        '{"search_query": "", "skip": true, "humor_ok": false, "humor_query": ""}',
    )

    assert result.knowledge_indexes == ()
    assert result.knowledge_query == ""


@pytest.mark.asyncio
async def test_turn_planner_parse_tone():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "срочно помоги с задачей",
        '{"should_reply": true, "search_query": "задача", "skip": false, '
        '"tone": "serious", "humor_ok": false, "humor_query": ""}',
    )

    assert result.tone == "serious"


@pytest.mark.asyncio
async def test_turn_planner_tone_defaults_neutral():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "ок",
        '{"search_query": "", "skip": true, "humor_ok": false, "humor_query": ""}',
    )

    assert result.tone == "neutral"


@pytest.mark.asyncio
async def test_turn_planner_tone_invalid_falls_back_neutral():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "test",
        '{"search_query": "x", "skip": false, "tone": "angry", '
        '"humor_ok": false, "humor_query": ""}',
    )

    assert result.tone == "neutral"


@pytest.mark.asyncio
async def test_turn_planner_fallback_tone_neutral():
    planner = TurnPlanner(use_llm=False)
    result = planner._fallback("привет")
    assert result.tone == "neutral"


@pytest.mark.asyncio
async def test_turn_planner_parse_needs_clarification():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "ванесса я думаю ты виновата",
        '{"should_reply": true, "search_query": "", "skip": false, '
        '"tone": "neutral", "humor_ok": false, "humor_query": "", '
        '"deep_search": false, "needs_clarification": true, '
        '"clarification_hint": "почему"}',
    )

    assert result.needs_clarification is True
    assert result.clarification_hint == "почему"
    assert result.should_reply is True
    assert result.skip_search is True
    assert result.text == ""


@pytest.mark.asyncio
async def test_turn_planner_needs_clarification_defaults_false():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "привет",
        '{"should_reply": true, "search_query": "", "skip": false, '
        '"humor_ok": false, "humor_query": ""}',
    )

    assert result.needs_clarification is False
    assert result.clarification_hint == ""


@pytest.mark.asyncio
async def test_turn_planner_fallback_needs_clarification_false():
    planner = TurnPlanner(use_llm=False)
    result = planner._fallback("привет")
    assert result.needs_clarification is False
