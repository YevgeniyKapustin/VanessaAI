import pytest

from vanessa.config.content import get_content
from vanessa.core.messages import ContextMessage
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.llm.planner.turn_planner import TurnPlanner


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
async def test_turn_planner_parse_decline_reason():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "чего и следовало ожидать",
        '{"should_reply": false, "search_query": "", "skip": true, '
        '"reason": "пустая фраза"}',
    )

    assert result.should_reply is False
    assert result.reason == "пустая фраза"


@pytest.mark.asyncio
async def test_turn_planner_reason_defaults_empty():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "привет",
        '{"should_reply": true, "search_query": "", "skip": false}',
    )

    assert result.reason == ""


def test_turn_planner_prompt_has_decline_reason_field():
    prompt = get_content().rag.turn_planner_prompt
    assert '"reason": ""' in prompt
    assert "## reason" in prompt


def test_turn_planner_prompt_teaches_imperative_address_is_not_self_talk():
    """A "ванесса + императив" message must be a direct address, not
    "общение между собой" — the exact misclassification being fixed."""
    prompt = get_content().rag.turn_planner_prompt
    assert "ванесса, не тормози, я написал" in prompt
    assert "общение между собой" in prompt
    # The prompt must state that a message naming/addressing the bot is NOT
    # "общение между собой".
    assert "naming the bot is not it" in prompt or "that names or addresses the bot is not it" in prompt
    # And the example section must show a direct imperative → should_reply=true.
    assert "«ванесса не тормози я написал»" in prompt


def test_turn_planner_prompt_teaches_repeated_message_is_spam():
    """The same sender sending the same message several times is junk —
    should_reply=false, skip=true — even short spam like «ванесса»."""
    prompt = get_content().rag.turn_planner_prompt
    assert "same sender sends the SAME message" in prompt
    assert "повтор сообщения" in prompt
    assert "spam burst" in prompt


def test_turn_planner_prompt_teaches_repeated_topic_loop():
    """Loop flag is anti-spam (empty re-asks), not anti deep-dive on one theme."""
    prompt = get_content().rag.turn_planner_prompt
    assert '"repeated_topic": false' in prompt
    assert '"loop_level": 0' in prompt
    assert "Repeated topic loop" in prompt
    assert "«по кругу»" in prompt
    assert "повтор темы" in prompt
    assert "anti-spam only" in prompt
    assert "not anti deep-dive" in prompt


@pytest.mark.asyncio
async def test_turn_planner_parse_loop_signal():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "ну так что там с мешем?",
        '{"should_reply": true, "search_query": "меш", "skip": false, '
        '"repeated_topic": true, "loop_level": 2, "reason": "повтор темы"}',
    )

    assert result.repeated_topic is True
    assert result.loop_level == 2


@pytest.mark.asyncio
async def test_turn_planner_loop_level_defaults_zero():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "привет",
        '{"should_reply": true, "search_query": "", "skip": false}',
    )

    assert result.repeated_topic is False
    assert result.loop_level == 0


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
    assert result.knowledge_detail is False


@pytest.mark.asyncio
async def test_turn_planner_parse_knowledge_detail():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "что там у Лича с работой",
        '{"search_query": "личь работа", "skip": false, "humor_ok": false, '
        '"humor_query": "", "knowledge_indexes": ["people"], '
        '"knowledge_query": "личь работа", "knowledge_detail": true}',
    )

    assert result.knowledge_indexes == ("people",)
    assert result.knowledge_detail is True


@pytest.mark.asyncio
async def test_turn_planner_knowledge_detail_defaults_false():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "кто такой Тик так",
        '{"search_query": "тик так", "skip": false, "humor_ok": false, '
        '"humor_query": "", "knowledge_indexes": ["people"], '
        '"knowledge_query": "тик так"}',
    )

    assert result.knowledge_detail is False


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


def test_turn_planner_prompt_forbids_markdown_json_wrapping():
    """The Output format section must demand raw JSON, not ```json fences."""
    prompt = get_content().rag.turn_planner_prompt
    assert "Output format" in prompt
    assert "Output ONLY valid raw JSON" in prompt
    assert "no ```json code fences" in prompt
    # the weak instruction is gone
    assert "JSON without markdown" not in prompt


def test_turn_planner_prompt_knowledge_indexes_selective():
    """knowledge_indexes must not fire on a passing name mention."""
    prompt = get_content().rag.turn_planner_prompt
    section = prompt.split("## knowledge_indexes", 1)[1].split("## Examples", 1)[0]
    # archives are secondary to direct history and queried selectively
    assert "secondary to direct message history" in section
    assert "should be queried" in section
    assert "selectively" in section
    # the old over-triggering rule is gone
    assert "still consider" not in section
    assert 'knowledge_indexes=["people","lore"]' not in section
    # the strict rule is present
    assert "do NOT trigger it just" in section
    assert "mentioned in passing" in section


def test_turn_planner_prompt_documents_knowledge_detail():
    """The prompt must teach the model when to request raw dossier facts."""
    prompt = get_content().rag.turn_planner_prompt
    section = prompt.split("## knowledge_detail", 1)[1].split("## Examples", 1)[0]
    assert "compact portrait" in section
    assert "raw dossier" in section
    assert "concrete fact" in section
    # Portrait-only is the default; raw facts only on an explicit fact question.
    assert "false (default)" in section
    assert "true — the user asks a concrete fact" in section


@pytest.mark.asyncio
async def test_turn_planner_parse_uses_pro_model():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "напиши скрипт на C#",
        '{"should_reply": true, "search_query": "скрипт", "skip": false, '
        '"humor_ok": false, "humor_query": "", "uses_pro_model": true}',
    )
    assert result.uses_pro_model is True


@pytest.mark.asyncio
async def test_turn_planner_uses_pro_model_defaults_false():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "привет",
        '{"should_reply": true, "search_query": "", "skip": false, '
        '"humor_ok": false, "humor_query": ""}',
    )
    assert result.uses_pro_model is False


def test_turn_planner_prompt_documents_uses_pro_model():
    """The gate prompt must teach when to escalate to the upscaled model."""
    prompt = get_content().rag.turn_planner_prompt
    section = prompt.split("## uses_pro_model", 1)[1].split("## Examples", 1)[0]
    assert "coding" in section
    assert "super-complex synthesis" in section
    assert "false (default)" in section
    assert "costs more" in section
    # The output template must include the field, defaulting to false.
    assert '"uses_pro_model": false' in prompt


def test_turn_planner_prompt_documents_detail():
    """The planner prompt must teach the desired reply-length field."""
    prompt = get_content().rag.turn_planner_prompt
    assert '"detail": "normal"' in prompt
    assert "## detail" in prompt
    assert '"detailed"' in prompt
    assert '"brief"' in prompt


@pytest.mark.asyncio
async def test_turn_planner_parse_detail():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "давай подробнее",
        '{"should_reply": true, "search_query": "", "skip": false, '
        '"detail": "detailed"}',
    )

    assert result.detail == "detailed"


@pytest.mark.asyncio
async def test_turn_planner_detail_defaults_normal():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "привет",
        '{"should_reply": true, "search_query": "", "skip": false}',
    )

    assert result.detail == "normal"


@pytest.mark.asyncio
async def test_turn_planner_detail_invalid_value_defaults_normal():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "привет",
        '{"should_reply": true, "search_query": "", "skip": false, '
        '"detail": "very-long"}',
    )

    assert result.detail == "normal"


def test_turn_planner_apply_detail_heuristic_overrides_planner():
    """Explicit «в двух словах» must beat the planner's wrong 'detailed'."""
    planner = TurnPlanner(use_llm=False)
    plan = TurnPlan(
        original="расскажи в двух словах",
        text="расскажи",
        skip_search=False,
        should_reply=True,
        detail="detailed",
    )

    result = planner._apply_detail(plan, "расскажи в двух словах")

    assert result.detail == "brief"


def test_turn_planner_apply_detail_keeps_planner_when_no_explicit_phrasing():
    """No explicit phrasing → the planner's implicit detail stands."""
    planner = TurnPlanner(use_llm=False)
    plan = TurnPlan(
        original="объясни как это работает",
        text="объясни как работает",
        skip_search=False,
        should_reply=True,
        detail="detailed",
    )

    result = planner._apply_detail(plan, "объясни как это работает")

    assert result.detail == "detailed"


def test_turn_planner_apply_detail_clarification_wins_over_heuristic():
    """A clarification turn stays a short question — «подробнее» must not force
    a detailed answer when the planner needs to ask for context."""
    planner = TurnPlanner(use_llm=False)
    plan = TurnPlan(
        original="про то самое, подробнее",
        text="",
        skip_search=True,
        should_reply=True,
        needs_clarification=True,
        detail="normal",
    )

    result = planner._apply_detail(plan, "про то самое, подробнее")

    assert result.detail == "normal"


@pytest.mark.asyncio
async def test_turn_planner_fallback_applies_detail_heuristic():
    """Even the no-LLM fallback path honors an explicit detail request."""
    planner = TurnPlanner(use_llm=False)

    result = await planner.prepare("давай более развёрнутый ответ")

    assert result.detail == "detailed"


class _FakeClient:
    """Minimal LLM chat completer that returns a valid planner JSON."""

    async def complete(self, model, messages, kind, **kwargs):
        return (
            '{"search_query": "x", "skip": false, "humor_ok": false, '
            '"humor_query": "", "should_reply": true}'
        )


@pytest.mark.asyncio
async def test_turn_planner_participants_provider_receives_message_and_recent():
    """The dynamic participants digest must get the turn's message + window."""
    received = []

    async def provider(message, recent_messages):
        received.append((message, recent_messages))
        return "крабер: отшельник"

    recent = [
        ContextMessage(id=1, role="user", content="крабер опять в пещере"),
        ContextMessage(id=2, role="assistant", content="ну и пусть"),
    ]
    planner = TurnPlanner(
        use_llm=True,
        llm_client=_FakeClient(),
        participants_provider=provider,
    )

    result = await planner.prepare(
        "расскажи про крабера",
        recent_messages=recent,
    )

    assert result.should_reply is True
    assert received == [("расскажи про крабера", recent)]


def test_turn_plan_to_trace_dict():
    """The Langfuse gate-span output must expose every planner decision."""
    plan = TurnPlan(
        original="во что играет Крабер?",
        text="крабер игры",
        skip_search=False,
        tone="neutral",
        humor_ok=True,
        humor_query="игры крабер",
        should_reply=True,
        deep_search=True,
        knowledge_indexes=("people",),
        knowledge_query="крабер",
        knowledge_detail=True,
        needs_clarification=False,
        uses_pro_model=False,
        detail="detailed",
    )
    data = plan.to_trace_dict()
    assert data["search_query"] == "крабер игры"
    assert data["skip_search"] is False
    assert data["should_reply"] is True
    assert data["tone"] == "neutral"
    assert data["humor_ok"] is True
    assert data["humor_query"] == "игры крабер"
    assert data["deep_search"] is True
    assert data["knowledge_indexes"] == ["people"]
    assert data["knowledge_query"] == "крабер"
    assert data["knowledge_detail"] is True
    assert data["needs_clarification"] is False
    assert data["uses_pro_model"] is False
    assert data["detail"] == "detailed"
    # The raw user message is already on the trace root — not duplicated here.
    assert "original" not in data


def test_turn_plan_to_trace_dict_includes_web_search():
    plan = TurnPlan(
        original="какая цена биткоина",
        text="bitcoin цена",
        skip_search=False,
        web_search=True,
        web_query="bitcoin цена сегодня",
    )
    data = plan.to_trace_dict()
    assert data["web_search"] is True
    assert data["web_query"] == "bitcoin цена сегодня"


def test_turn_planner_parses_web_search_flag():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "какая цена биткоина",
        '{"should_reply": true, "search_query": "bitcoin цена", "skip": false, '
        '"web_search": true, "web_query": "bitcoin цена сегодня"}',
    )
    assert result.web_search is True
    assert result.web_query == "bitcoin цена сегодня"


def test_turn_planner_web_search_falls_back_to_search_query():
    """A flagged web search with an empty web_query uses search_query instead."""
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "какая цена биткоина",
        '{"should_reply": true, "search_query": "bitcoin цена", "skip": false, '
        '"web_search": true, "web_query": ""}',
    )
    assert result.web_search is True
    assert result.web_query == "bitcoin цена"


def test_turn_planner_web_search_defaults_off():
    planner = TurnPlanner(use_llm=False)
    result = planner._parse_llm_response(
        "расскажи про крабера",
        '{"should_reply": true, "search_query": "крабер", "skip": false}',
    )
    assert result.web_search is False
    assert result.web_query == ""


def test_turn_planner_prompt_teaches_web_search():
    prompt = get_content().rag.turn_planner_prompt
    assert '"web_search": false' in prompt
    assert '"web_query": ""' in prompt
    assert "## web_search / web_query" in prompt
    assert "web_search=true" in prompt
