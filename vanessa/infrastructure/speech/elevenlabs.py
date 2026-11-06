"""Thin ElevenLabs HTTP client: speech synthesis and voice-note transcription.

One class, two directions, no SDK — tests mock the ``client``. PCM goes to the
presence adapter for visemes; Telegram asks for MP3 and sends it as a voice
note, so no audio conversion ever runs in our containers.
"""

from __future__ import annotations

import logging

import httpx

from vanessa.config.settings import settings
from vanessa.core.protocols.speech import SpeechAudio
from vanessa.infrastructure.speech.pcm import sample_rate_from_output_format

logger = logging.getLogger(__name__)

_ELEVENLABS_BASE = "https://api.elevenlabs.io"
_STT_AUDIO_MIME = "audio/ogg"


class ElevenLabsSpeech:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        voice_id: str | None = None,
        model_id: str | None = None,
        stt_model_id: str | None = None,
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
        self._stt_model_id = (
            stt_model_id
            if stt_model_id is not None
            else settings.elevenlabs_stt_model_id
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

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {"xi-api-key": self._api_key.strip()}

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

    async def transcribe(self, audio: bytes, *, filename: str) -> str | None:
        if not audio:
            return None
        if not self._api_key.strip():
            logger.warning("elevenlabs_stt_no_credentials bytes=%s", len(audio))
            return None
        response = await self._post_transcription(audio, filename)
        response.raise_for_status()
        return _text_from_body(response)

    async def _post(self, text: str) -> httpx.Response:
        url = f"{_ELEVENLABS_BASE}/v1/text-to-speech/{self._voice_id.strip()}"
        return await self._http.post(
            url,
            params={"output_format": self._output_format},
            headers={**self._auth_headers, "accept": "application/octet-stream"},
            json={"text": text, "model_id": self._model_id},
        )

    async def _post_transcription(self, audio: bytes, filename: str) -> httpx.Response:
        return await self._http.post(
            f"{_ELEVENLABS_BASE}/v1/speech-to-text",
            headers={**self._auth_headers, "accept": "application/json"},
            files={"file": (filename, audio, _STT_AUDIO_MIME)},
            data={"model_id": self._stt_model_id},
        )


def _audio_from_body(body: bytes, sample_rate: int) -> SpeechAudio | None:
    if not body:
        return None
    return SpeechAudio(pcm=body, sample_rate=sample_rate)


def _text_from_body(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        logger.warning("elevenlabs_stt_unreadable_body")
        return None
    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        return None
    return text.strip()
