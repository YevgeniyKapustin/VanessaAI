from __future__ import annotations

from collections.abc import Callable

from vanessa.core import SpeechAudio, SpeechSynthesizer
from vanessa.infrastructure.speech import create_speech_synthesizer

_EMPTY_RATE = 24_000


class NullSynthesizer:
    async def synthesize(self, text: str) -> SpeechAudio | None:
        del text
        return SpeechAudio(pcm=b"", sample_rate=_EMPTY_RATE)


def load_synthesizer() -> SpeechSynthesizer:
    return _call_factory(create_speech_synthesizer)


def _call_factory(factory: Callable[[], SpeechSynthesizer]) -> SpeechSynthesizer:
    try:
        return factory()
    except (TypeError, OSError, ValueError):
        return NullSynthesizer()
