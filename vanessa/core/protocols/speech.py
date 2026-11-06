from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SpeechAudio:
    """Raw 16-bit little-endian mono PCM. Never travels on Redis / TurnReply."""

    pcm: bytes
    sample_rate: int


class SpeechSynthesizer(Protocol):
    """Text → PCM. Adapters (bot, presence) own playback; the agent stays text."""

    async def synthesize(self, text: str) -> SpeechAudio | None: ...


class SpeechTranscriber(Protocol):
    """Voice note → text. Telegram voice notes only; the agent stays text."""

    async def transcribe(self, audio: bytes, *, filename: str) -> str | None: ...
