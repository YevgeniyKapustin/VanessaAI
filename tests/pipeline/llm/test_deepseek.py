from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIStatusError

from vanessa.config.content import get_content
from vanessa.config.settings import settings
from vanessa.core.messages import ContextBlock, ContextMessage, ImageAttachment
from vanessa.pipeline.llm.planner.generation_config import LLMGenerationParams
from vanessa.pipeline.llm.providers.deepseek import DeepSeekLLMProvider, _usage_from_openai


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
    # The fixture's generation params carry no reasoning_effort → not forwarded.
    assert "reasoning_effort" not in call.kwargs


@pytest.mark.asyncio
async def test_deepseek_forwards_reasoning_effort_when_configured():
    # The composer runs on a DeepSeek V4 (thinking) model with reasoning_effort
    # forced high — the chain of thought must be requested from the API.
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_response("привет мир")
    )
    provider = DeepSeekLLMProvider(
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
    call = provider._client.chat.completions.create.await_args
    assert call.kwargs["reasoning_effort"] == "high"


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
    with patch("vanessa.pipeline.llm.providers.deepseek.asyncio.sleep", new_callable=AsyncMock):
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


@pytest.mark.asyncio
async def test_deepseek_generate_forwards_detail_and_bumps_max_tokens(
    provider: DeepSeekLLMProvider,
):
    await provider.generate(
        "давай подробнее",
        [],
        detail="detailed",
    )
    call = provider._client.chat.completions.create.await_args
    user_prompt = call.kwargs["messages"][1]["content"]
    assert get_content().llm.detail_note_detailed.strip() in user_prompt
    assert call.kwargs["max_tokens"] == get_content().llm.detailed_max_tokens


@pytest.mark.asyncio
async def test_deepseek_generate_keeps_base_max_tokens_for_normal(
    provider: DeepSeekLLMProvider,
):
    await provider.generate("привет", [], detail="normal")
    call = provider._client.chat.completions.create.await_args
    assert call.kwargs["max_tokens"] == 128


@pytest.mark.asyncio
async def test_deepseek_vision_routes_vision_model_and_sends_image_blocks(
    provider: DeepSeekLLMProvider,
):
    image = ImageAttachment(
        data_url="data:image/jpeg;base64,AAAA",
        mime_type="image/jpeg",
        telegram_file_id="file-1",
    )
    await provider.generate("что на фото", [], images=[image])

    call = provider._client.chat.completions.create.await_args
    # Images route the call to the vision model (not the default/pro model).
    assert call.kwargs["model"] == settings.deepseek_vision_model
    # The user content becomes a list of OpenAI multimodal blocks: text + image_url.
    user_content = call.kwargs["messages"][1]["content"]
    assert isinstance(user_content, list)
    assert user_content[0]["type"] == "text"
    assert "что на фото" in user_content[0]["text"]
    # The vision instruction is injected so the model knows it can see an image.
    assert get_content().llm.vision_note.strip() in user_content[0]["text"]
    assert user_content[1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/jpeg;base64,AAAA"},
    }


@pytest.mark.asyncio
async def test_deepseek_plain_content_stays_string_without_images(
    provider: DeepSeekLLMProvider,
):
    await provider.generate("hello", [])
    call = provider._client.chat.completions.create.await_args
    # Backwards compatible: no images -> the prompt stays a plain string.
    assert isinstance(call.kwargs["messages"][1]["content"], str)
    assert call.kwargs["model"] == "test-model"


@pytest.mark.asyncio
async def test_deepseek_vision_caps_images_per_turn(
    provider: DeepSeekLLMProvider,
):
    # The provider itself does not cap — the ComposeStage does — but it must
    # attach exactly the images it is given and route them all as blocks.
    images = [
        ImageAttachment(data_url=f"data:image/jpeg;base64,{i}", mime_type="image/jpeg")
        for i in range(2)
    ]
    await provider.generate("фото", [], images=images)
    call = provider._client.chat.completions.create.await_args
    user_content = call.kwargs["messages"][1]["content"]
    image_blocks = [b for b in user_content if b["type"] == "image_url"]
    assert len(image_blocks) == 2


@pytest.mark.asyncio
async def test_deepseek_photo_candidates_injected_into_prompt(
    provider: DeepSeekLLMProvider,
):
    from vanessa.core.messages import PhotoCandidate

    candidates = [
        PhotoCandidate(
            index=1,
            telegram_file_id="f1",
            caption="кот на диване",
            sender_name="Тест",
        )
    ]
    await provider.generate("скинь фото с котом", [], photo_candidates=candidates)

    call = provider._client.chat.completions.create.await_args
    content = call.kwargs["messages"][1]["content"]
    text = content[0]["text"] if isinstance(content, list) else content
    assert get_content().llm.photo_album_header.strip() in text
    assert "кот на диване" in text
    assert "[photo:1]" in text or "[photo:<index>]" in text


@pytest.mark.asyncio
async def test_deepseek_web_blocks_injected_into_prompt(provider: DeepSeekLLMProvider):
    """The compose prompt carries the live web-results block verbatim."""
    from vanessa.core.messages import WebResult

    results = [
        WebResult(
            title="Bitcoin price",
            url="https://example.com/btc",
            snippet="Bitcoin is trading at 100k",
            published_date="2026-08-28",
        )
    ]
    await provider.generate("какая цена биткоина", [], web_blocks=results)

    call = provider._client.chat.completions.create.await_args
    content = call.kwargs["messages"][1]["content"]
    text = content[0]["text"] if isinstance(content, list) else content
    assert get_content().llm.web_header.strip() in text
    assert "Bitcoin price (https://example.com/btc):" in text
    assert "Bitcoin is trading at 100k" in text
    assert "[2026-08-28]" in text
    assert "LIVE search results" in text
