"""Adapter-side speech. Presence and bot import this; audio never goes on Redis."""

from vanessa.core.protocols.speech import (
    SpeechAudio,
    SpeechSynthesizer,
    SpeechTranscriber,
)
from vanessa.infrastructure.speech.elevenlabs import ElevenLabsSpeech
from vanessa.infrastructure.speech.factory import create_speech_synthesizer
from vanessa.infrastructure.speech.pcm import pcm_to_wav, sample_rate_from_output_format
from vanessa.infrastructure.speech.text import speakable_text
from vanessa.infrastructure.speech.visemes import VisemeFrame, visemes_from_pcm
from vanessa.infrastructure.speech.voice import voice_payload

__all__ = [
    "ElevenLabsSpeech",
    "SpeechAudio",
    "SpeechSynthesizer",
    "SpeechTranscriber",
    "VisemeFrame",
    "create_speech_synthesizer",
    "pcm_to_wav",
    "sample_rate_from_output_format",
    "speakable_text",
    "visemes_from_pcm",
    "voice_payload",
]
