from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic import APIStatusError

from vanessa.config.content import get_content
from vanessa.core.messages import ContextBlock, ContextMessage
from vanessa.pipeline.llm.planner.generation_config import LLMGenerationParams
from vanessa.pipeline.llm.providers.claude import ClaudeLLMProvider


class FakeSubstitutor:
    def apply(self, text: str) -> str:
        return text.replace("bad", "блин")


@pytest.fixture
def provider() -> ClaudeLLMProvider:
    client = AsyncMock()
    response = MagicMock()
    response.content = [MagicMock(text="привет мир")]
    client.messages.create = AsyncMock(return_value=response)
    return ClaudeLLMProvider(
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
async def test_claude_generate_returns_capitalized_reply(provider: ClaudeLLMProvider):
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
    provider._client.messages.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_claude_never_sends_reasoning_effort():
    # The composer profile may carry reasoning_effort (a DeepSeek-only V4 param).
    # Claude must strip it — sending an unknown parameter would 400.
    client = AsyncMock()
    response = MagicMock()
    response.content = [MagicMock(text="привет мир")]
    client.messages.create = AsyncMock(return_value=response)
    provider = ClaudeLLMProvider(
        client=client,
        model="test-model",
        profanity_substitutor=FakeSubstitutor(),
        max_retries=1,
        generation=LLMGenerationParams(
            temperature=0.8,
            top_p=0.9,
            max_tokens=128,
            reasoning_effort="high",
        ),
    )
    await provider.generate("hello", [])
    call = provider._client.messages.create.await_args
    assert "reasoning_effort" not in call.kwargs


@pytest.mark.asyncio
async def test_claude_generate_strips_leading_sender_name(
    provider: ClaudeLLMProvider,
):
    provider._client.messages.create = AsyncMock(
        return_value=MagicMock(content=[MagicMock(text="Евгений, привет мир")])
    )
    reply = await provider.generate("hello", [], sender_name="Евгений")
    # The leading name-address is removed before capitalization.
    assert reply == "Привет мир"


@pytest.mark.asyncio
async def test_claude_generate_returns_only_after_answer_tag(
    provider: ClaudeLLMProvider,
):
    provider._client.messages.create = AsyncMock(
        return_value=MagicMock(
            content=[
                MagicMock(
                    text="Подумала: про крабера надо коротко.\n\n"
                    "[answer]\n"
                    "Крабер — местный, у него своя пещера."
                )
            ]
        )
    )
    reply = await provider.generate("что там с крабером", [])
    # The chain-of-thought reasoning before the tag must never reach the reply;
    # the trailing period is stripped by the standard post-processing.
    assert reply == "Крабер — местный, у него своя пещера"
    assert "Подумала" not in reply


@pytest.mark.asyncio
async def test_claude_generate_traces_reasoning(provider: ClaudeLLMProvider):
    from contextlib import asynccontextmanager

    from vanessa.infrastructure.observability.tracing import set_tracer

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
        provider._client.messages.create = AsyncMock(
            return_value=MagicMock(
                content=[MagicMock(text="Подумала: кратко.\n[answer]\nКрабер — местный.")]
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
async def test_claude_retries_on_rate_limit(provider: ClaudeLLMProvider):
    ok = MagicMock()
    ok.content = [MagicMock(text="ok")]
    request = MagicMock()
    request.headers = {}
    rate_limit = APIStatusError(
        "rate limited",
        response=MagicMock(status_code=429, headers={}),
        body=None,
    )
    provider._client.messages.create = AsyncMock(
        side_effect=[rate_limit, ok],
    )
    with patch("vanessa.pipeline.llm.providers.claude.asyncio.sleep", new_callable=AsyncMock):
        reply = await provider.generate("retry me", [])
    assert reply == "Ok"
    assert provider._client.messages.create.await_count == 2


def test_should_retry_only_transient_errors(provider: ClaudeLLMProvider):
    transient = MagicMock(spec=APIStatusError)
    transient.status_code = 503
    fatal = MagicMock(spec=APIStatusError)
    fatal.status_code = 400
    assert provider._should_retry(transient) is True
    assert provider._should_retry(fatal) is False
    assert provider._should_retry(RuntimeError("x")) is False


@pytest.mark.asyncio
async def test_claude_generate_includes_clarification_instruction(
    provider: ClaudeLLMProvider,
):
    await provider.generate(
        "ванесса я думаю ты виновата",
        [],
        needs_clarification=True,
        clarification_hint="почему",
    )
    call = provider._client.messages.create.await_args
    user_prompt = call.kwargs["messages"][0]["content"]
    assert get_content().llm.clarification_instruction.strip() in user_prompt
    assert "What is unclear: почему" in user_prompt


@pytest.mark.asyncio
async def test_claude_generate_forwards_brief_note(provider: ClaudeLLMProvider):
    await provider.generate(
        "в двух словах",
        [],
        detail="brief",
    )
    call = provider._client.messages.create.await_args
    user_prompt = call.kwargs["messages"][0]["content"]
    assert get_content().llm.detail_note_brief.strip() in user_prompt


@pytest.mark.asyncio
async def test_claude_generate_bumps_max_tokens_for_detailed(
    provider: ClaudeLLMProvider,
):
    await provider.generate("давай подробнее", [], detail="detailed")
    call = provider._client.messages.create.await_args
    assert call.kwargs["max_tokens"] == get_content().llm.detailed_max_tokens
