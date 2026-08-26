from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIStatusError

from app.core.messages import ContextBlock, ContextMessage
from app.llm.planner.generation_config import LLMGenerationParams
from app.llm.providers.deepseek import DeepSeekLLMProvider


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
async def test_deepseek_generate_includes_critic_feedback(provider: DeepSeekLLMProvider):
    await provider.generate("hello", [], critic_feedback="добавь больше иронии")
    call = provider._client.chat.completions.create.await_args
    user_prompt = call.kwargs["messages"][1]["content"]
    assert "Humor editor's note" in user_prompt
    assert "добавь больше иронии" in user_prompt
