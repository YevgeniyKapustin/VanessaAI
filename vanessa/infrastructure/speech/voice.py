"""TTS bytes → a Telegram voice-note payload.

ElevenLabs returns whatever format was asked for: MP3 for the bot (a voice note
Telegram accepts as-is), PCM for the presence adapter (visemes need raw
samples). The filename tells Telegram how to play it.
"""

from __future__ import annotations

from vanessa.core.protocols.speech import SpeechAudio
from vanessa.infrastructure.speech.pcm import pcm_to_wav

_MP3_PREFIX = "mp3_"
_PCM_PREFIX = "pcm_"
_MP3_NAME = "voice.mp3"
_OGG_NAME = "voice.ogg"
_WAV_NAME = "voice.wav"


def voice_payload(audio: SpeechAudio, *, output_format: str) -> tuple[bytes, str]:
    """Return ``(bytes, filename)`` for ``send_voice`` in the requested format."""
    fmt = (output_format or "").strip().lower()
    if fmt.startswith(_PCM_PREFIX):
        return pcm_to_wav(audio.pcm, audio.sample_rate), _WAV_NAME
    if fmt.startswith(_MP3_PREFIX):
        return audio.pcm, _MP3_NAME
    return audio.pcm, _OGG_NAME
