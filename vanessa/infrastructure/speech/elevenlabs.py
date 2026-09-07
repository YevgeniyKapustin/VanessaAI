"""Thin ElevenLabs HTTP TTS client (PCM). Mock ``client`` in tests; no SDK."""

from __future__ import annotations

import logging

import httpx

from vanessa.config.settings import settings
from vanessa.core.protocols.speech import SpeechAudio
from vanessa.infrastructure.speech.pcm import sample_rate_from_output_format

logger = logging.getLogger(__name__)

_ELEVENLABS_BASE = "https://api.elevenlabs.io"


class ElevenLabsSpeech:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        voice_id: str | None = None,
        model_id: str | None = None,
        output_format: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.elevenlabs_api_key
        self._voice_id = (
            voice_id if voice_id is not None else settings.elevenlabs_voice_id
        )
        self._model_id = (
            model_id if model_id is not None else settings.elevenlabs_model_id
        )
        self._output_format = (
            output_format
            if output_format is not None
            else settings.elevenlabs_output_format
        )
        self._client = client
        self._timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.elevenlabs_timeout_seconds
        )
        self._sample_rate = sample_rate_from_output_format(self._output_format)

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def synthesize(self, text: str) -> SpeechAudio | None:
        stripped = text.strip()
        if not stripped:
            return None
        if not self._api_key.strip() or not self._voice_id.strip():
            logger.warning(
                "elevenlabs_speech_no_credentials text_len=%s",
                len(stripped),
            )
            return None
        response = await self._post(stripped)
        response.raise_for_status()
        return _audio_from_body(response.content, self._sample_rate)

    async def _post(self, text: str) -> httpx.Response:
        url = f"{_ELEVENLABS_BASE}/v1/text-to-speech/{self._voice_id.strip()}"
        return await self._http.post(
            url,
            params={"output_format": self._output_format},
            headers={
                "xi-api-key": self._api_key.strip(),
                "accept": "application/octet-stream",
            },
            json={"text": text, "model_id": self._model_id},
        )


def _audio_from_body(body: bytes, sample_rate: int) -> SpeechAudio | None:
    if not body:
        return None
    return SpeechAudio(pcm=body, sample_rate=sample_rate)
