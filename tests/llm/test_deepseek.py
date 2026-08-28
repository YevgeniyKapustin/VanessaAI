from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIStatusError

from app.config.content import get_content
from app.core.messages import ContextBlock, ContextMessage
from app.llm.planner.generation_config import LLMGenerationParams
from app.llm.providers.deepseek import DeepSeekLLMProvider, _usage_from_openai


class FakeSubstitutor:
    def apply(self, text: str) -> str:
        return text.replace("bad", "блин")


def _make_response(text: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = text
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.fixture
def provider() -> DeepSeekLLMProvider:
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_response("привет мир")
    )
    return DeepSeekLLMProvider(
        client=client,
        model="test-model",
        profanity_substitutor=FakeSubstitutor(),
        max_retries=1,
        generation=LLMGenerationParams(
            temperature=0.8,
            top_p=0.9,
            max_tokens=128,
        ),
    )


@pytest.mark.asyncio
async def test_deepseek_generate_returns_capitalized_reply(provider: DeepSeekLLMProvider):
    blocks = [
        ContextBlock(
            anchor_id=1,
            messages=(
                ContextMessage(id=1, role="user", content="context"),
            ),
        )
    ]
    reply = await provider.generate("hello", blocks, sender_name="Test")
    assert reply == "Привет мир"
    provider._client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_deepseek_uses_default_model_by_default(provider: DeepSeekLLMProvider):
    await provider.generate("hello", [])
    call = provider._client.chat.completions.create.await_args
    assert call.kwargs["model"] == "test-model"
    # Gate/compose never send reasoning_effort (default normal mode).
    assert "reasoning_effort" not in call.kwargs


@pytest.mark.asyncio
async def test_deepseek_routes_pro_model_when_flagged(provider: DeepSeekLLMProvider):
    await provider.generate("напиши код на C#", [], uses_pro_model=True)
    call = provider._client.chat.completions.create.await_args
    assert call.kwargs["model"] == "deepseek-v4-pro"


def test_usage_from_openai_includes_cache_tokens():
    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 20
    usage.total_tokens = 120
    usage.prompt_cache_hit_tokens = 90
    usage.prompt_cache_miss_tokens = 10
    response = MagicMock()
    response.usage = usage
    assert _usage_from_openai(response) == {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
        "cache_hit_tokens": 90,
        "cache_miss_tokens": 10,
    }


def test_usage_from_openai_without_cache_fields_defaults_zero():
    usage = MagicMock()
    usage.prompt_tokens = 5
    usage.completion_tokens = 1
    usage.total_tokens = 6
    # prompt_cache_hit_tokens / prompt_cache_miss_tokens are absent (e.g. non-V4).
    del usage.prompt_cache_hit_tokens
    del usage.prompt_cache_miss_tokens
    response = MagicMock()
    response.usage = usage
    normalized = _usage_from_openai(response)
    assert normalized["cache_hit_tokens"] == 0
    assert normalized["cache_miss_tokens"] == 0


@pytest.mark.asyncio
async def test_deepseek_generate_strips_leading_sender_name(
    provider: DeepSeekLLMProvider,
):
    provider._client.chat.completions.create = AsyncMock(
        return_value=_make_response("Евгений, привет мир")
    )
    reply = await provider.generate("hello", [], sender_name="Евгений")
    # The leading name-address is removed before capitalization.
    assert reply == "Привет мир"


@pytest.mark.asyncio
async def test_deepseek_generate_returns_only_after_answer_tag(
    provider: DeepSeekLLMProvider,
):
    provider._client.chat.completions.create = AsyncMock(
        return_value=_make_response(
            "Подумала: про крабера надо коротко.\n\n"
            "[answer]\n"
            "Крабер — местный, у него своя пещера."
        )
    )
    reply = await provider.generate("что там с крабером", [])
    # The chain-of-thought reasoning before the tag must never reach the reply;
    # the trailing period is stripped by the standard post-processing.
    assert reply == "Крабер — местный, у него своя пещера"
    assert "Подумала" not in reply


@pytest.mark.asyncio
async def test_deepseek_generate_traces_reasoning(provider: DeepSeekLLMProvider):
    from contextlib import asynccontextmanager

    from app.observability.tracing import set_tracer

    class RecordingSpan:
        def __init__(self) -> None:
            self.updates: list[dict] = []

        def update(self, **kwargs) -> None:
            self.updates.append(kwargs)

    class RecordingTracer:
        enabled = True

        def __init__(self, span: RecordingSpan) -> None:
            self._span = span

        @asynccontextmanager
        async def generation(self, *, name, model=None, input=None, output=None,
                             usage=None, metadata=None):
            del name, model, input, output, usage, metadata
            yield self._span

    span = RecordingSpan()
    set_tracer(RecordingTracer(span))
    try:
        provider._client.chat.completions.create = AsyncMock(
            return_value=_make_response(
                "Подумала: кратко.\n[answer]\nКрабер — местный."
            )
        )
        await provider.generate("что там с крабером", [])
    finally:
        set_tracer(None)

    assert any(
        update.get("metadata", {}).get("reasoning") == "Подумала: кратко."
        for update in span.updates
    )


@pytest.mark.asyncio
async def test_deepseek_retries_on_rate_limit(provider: DeepSeekLLMProvider):
    rate_limit = APIStatusError(
        "rate limited",
        response=MagicMock(status_code=429, headers={}),
        body=None,
    )
    provider._client.chat.completions.create = AsyncMock(
        side_effect=[rate_limit, _make_response("ok")],
    )
    with patch("app.llm.providers.deepseek.asyncio.sleep", new_callable=AsyncMock):
        reply = await provider.generate("retry me", [])
    assert reply == "Ok"
    assert provider._client.chat.completions.create.await_count == 2


def test_should_retry_only_transient_errors(provider: DeepSeekLLMProvider):
    transient = MagicMock(spec=APIStatusError)
    transient.status_code = 503
    fatal = MagicMock(spec=APIStatusError)
    fatal.status_code = 400
    assert provider._should_retry(transient) is True
    assert provider._should_retry(fatal) is False
    assert provider._should_retry(RuntimeError("x")) is False


@pytest.mark.asyncio
async def test_deepseek_generate_includes_clarification_instruction(
    provider: DeepSeekLLMProvider,
):
    await provider.generate(
        "ванесса я думаю ты виновата",
        [],
        needs_clarification=True,
        clarification_hint="почему",
    )
    call = provider._client.chat.completions.create.await_args
    user_prompt = call.kwargs["messages"][1]["content"]
    assert get_content().llm.clarification_instruction.strip() in user_prompt
    assert "What is unclear: почему" in user_prompt
