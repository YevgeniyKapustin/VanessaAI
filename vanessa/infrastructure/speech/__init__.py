"""Adapter-side TTS. Presence and bot import this; wav never goes on Redis."""

from vanessa.core.protocols.speech import SpeechAudio, SpeechSynthesizer
from vanessa.infrastructure.speech.elevenlabs import ElevenLabsSpeech
from vanessa.infrastructure.speech.factory import create_speech_synthesizer
from vanessa.infrastructure.speech.pcm import pcm_to_wav, sample_rate_from_output_format
from vanessa.infrastructure.speech.visemes import VisemeFrame, visemes_from_pcm

__all__ = [
    "ElevenLabsSpeech",
    "SpeechAudio",
    "SpeechSynthesizer",
    "VisemeFrame",
    "create_speech_synthesizer",
    "pcm_to_wav",
    "sample_rate_from_output_format",
    "visemes_from_pcm",
]
