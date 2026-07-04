from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic import APIStatusError

from app.core.messages import ContextBlock, ContextMessage
from app.llm.planner.generation_config import LLMGenerationParams
from app.llm.providers.claude import ClaudeLLMProvider


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
    with patch("app.llm.providers.claude.asyncio.sleep", new_callable=AsyncMock):
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
