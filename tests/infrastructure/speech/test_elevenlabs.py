from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from vanessa.infrastructure.speech import create_speech_synthesizer
from vanessa.infrastructure.speech.elevenlabs import ElevenLabsSpeech

_PCM_RATE = 24_000
_HTTP_OK = 200
_HTTP_UNAUTHORIZED = 401


def _pcm_client(body: bytes, *, status: int = _HTTP_OK) -> AsyncMock:
    client = AsyncMock()
    response = MagicMock()
    response.content = body
    if status != _HTTP_OK:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "tts failed",
            request=MagicMock(),
            response=MagicMock(status_code=status),
        )
    else:
        response.raise_for_status.return_value = None
    client.post.return_value = response
    return client


@pytest.mark.asyncio
async def test_synthesize_posts_pcm_request() -> None:
    pcm = b"\x01\x00\x02\x00"
    client = _pcm_client(pcm)
    speech = ElevenLabsSpeech(
        api_key="xi-test",
        voice_id="voice-1",
        model_id="eleven_multilingual_v2",
        output_format="pcm_24000",
        client=client,
    )
    audio = await speech.synthesize("  привет  ")

    assert audio is not None
    assert audio.pcm == pcm
    assert audio.sample_rate == _PCM_RATE
    call = client.post.await_args
    assert call.args[0].endswith("/v1/text-to-speech/voice-1")
    assert call.kwargs["params"]["output_format"] == "pcm_24000"
    assert call.kwargs["headers"]["xi-api-key"] == "xi-test"
    assert call.kwargs["json"]["text"] == "привет"
    assert call.kwargs["json"]["model_id"] == "eleven_multilingual_v2"


@pytest.mark.asyncio
async def test_synthesize_skips_without_credentials() -> None:
    client = AsyncMock()
    speech = ElevenLabsSpeech(api_key="", voice_id="voice-1", client=client)
    assert await speech.synthesize("hello") is None
    client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_synthesize_skips_blank_text() -> None:
    client = AsyncMock()
    speech = ElevenLabsSpeech(api_key="xi-test", voice_id="voice-1", client=client)
    assert await speech.synthesize("   ") is None
    client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_synthesize_empty_body_returns_none() -> None:
    client = _pcm_client(b"")
    speech = ElevenLabsSpeech(api_key="xi-test", voice_id="voice-1", client=client)
    assert await speech.synthesize("hello") is None


@pytest.mark.asyncio
async def test_synthesize_http_error_propagates() -> None:
    client = _pcm_client(b"", status=_HTTP_UNAUTHORIZED)
    speech = ElevenLabsSpeech(api_key="xi-test", voice_id="voice-1", client=client)
    with pytest.raises(httpx.HTTPStatusError):
        await speech.synthesize("hello")


def test_factory_returns_elevenlabs_client() -> None:
    assert isinstance(create_speech_synthesizer(), ElevenLabsSpeech)


@pytest.mark.asyncio
async def test_synthesize_builds_httpx_client(monkeypatch) -> None:
    pcm = b"\x03\x00"
    captured: list[httpx.AsyncClient] = []

    class FakeAsyncClient:
        def __init__(self, **kwargs) -> None:
            del kwargs
            captured.append(self)
            self.post = AsyncMock(return_value=_pcm_client(pcm).post.return_value)

    monkeypatch.setattr(
        "vanessa.infrastructure.speech.elevenlabs.httpx.AsyncClient",
        FakeAsyncClient,
    )
    speech = ElevenLabsSpeech(api_key="xi-test", voice_id="voice-1")
    audio = await speech.synthesize("hello")
    assert audio is not None
    assert audio.pcm == pcm
    assert captured
