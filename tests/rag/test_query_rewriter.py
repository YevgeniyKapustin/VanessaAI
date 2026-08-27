from unittest.mock import AsyncMock, patch

import pytest

from app.rag.query_rewriter import QueryRewriter


@pytest.fixture
def rewriter() -> QueryRewriter:
    return QueryRewriter(use_llm=False)


@pytest.mark.asyncio
async def test_fallback_uses_original_message(rewriter: QueryRewriter):
    result = await rewriter.prepare("расскажи про крабера")

    assert result.text == "расскажи про крабера"
    assert result.skip_search is False


@pytest.mark.asyncio
async def test_fallback_skips_empty_message(rewriter: QueryRewriter):
    result = await rewriter.prepare("   ")

    assert result.text == ""
    assert result.skip_search is True


@pytest.mark.asyncio
async def test_parse_llm_skip():
    rewriter = QueryRewriter(use_llm=False)
    result = rewriter._parse_llm_response(
        "ванесса привет",
        '{"search_query": "", "skip": true}',
    )

    assert result.skip_search is True
    assert result.text == ""


@pytest.mark.asyncio
async def test_parse_llm_search_query():
    rewriter = QueryRewriter(use_llm=False)
    result = rewriter._parse_llm_response(
        "расскажи про крабера",
        '{"search_query": "крабер", "skip": false}',
    )

    assert result.skip_search is False
    assert result.text == "крабер"


@pytest.mark.asyncio
async def test_parse_llm_decline_reason(rewriter):
    result = rewriter._parse_llm_response(
        "чего и следовало ожидать",
        '{"search_query": "", "skip": true, "reason": "пустая фраза"}',
    )

    assert result.skip_search is True
    assert result.reason == "пустая фраза"


@pytest.mark.asyncio
async def test_parse_llm_plain_text_fallback():
    rewriter = QueryRewriter(use_llm=False)
    result = rewriter._parse_llm_response("original", "крабер")

    assert result.text == "крабер"
    assert result.skip_search is False


@pytest.mark.asyncio
async def test_llm_rewrite_called_when_enabled():
    rewriter = QueryRewriter(use_llm=True)
    with patch.object(
        rewriter,
        "_plan_with_llm",
        new=AsyncMock(
            return_value=rewriter._parse_llm_response(
                "расскажи про крабера",
                '{"search_query": "крабер", "skip": false}',
            ),
        ),
    ) as mock_llm:
        result = await rewriter.prepare("расскажи про крабера")

    mock_llm.assert_awaited_once()
    assert result.text == "крабер"


@pytest.mark.asyncio
async def test_llm_failure_uses_fallback():
    rewriter = QueryRewriter(use_llm=True)
    with patch.object(
        rewriter,
        "_plan_with_llm",
        new=AsyncMock(side_effect=RuntimeError("api down")),
    ):
        result = await rewriter.prepare("расскажи про крабера")

    assert result.text == "расскажи про крабера"
    assert result.skip_search is False


class _FakeCompleter:
    def __init__(self) -> None:
        self.prompt: str | None = None

    async def complete(self, model, messages, **kwargs):
        self.prompt = messages[0]["content"]
        return '{"search_query": "личь сварщик", "skip": false, "humor_ok": false, "humor_query": ""}'


@pytest.mark.asyncio
async def test_llm_prompt_includes_participants():
    async def provider(message, recent_messages) -> str:
        return "Личь — сварщик, играет в ХСР. Крабер — любит пещеры."

    client = _FakeCompleter()
    rewriter = QueryRewriter(
        use_llm=True,
        llm_client=client,
        participants_provider=provider,
    )

    await rewriter.prepare("что там у Лича с работой")

    assert client.prompt is not None
    assert "Личь — сварщик" in client.prompt


@pytest.mark.asyncio
async def test_llm_prompt_participants_failure_uses_placeholder():
    async def provider(message, recent_messages) -> str:
        raise RuntimeError("vault down")

    client = _FakeCompleter()
    rewriter = QueryRewriter(
        use_llm=True,
        llm_client=client,
        participants_provider=provider,
    )

    result = await rewriter.prepare("расскажи про крабера")

    assert result.text == "личь сварщик"
    assert "(нет данных)" in client.prompt
