from vanessa.infrastructure.speech.elevenlabs import ElevenLabsSpeech


def create_speech_synthesizer(*, output_format: str | None = None) -> ElevenLabsSpeech:
    """Build the TTS client; ``output_format`` overrides the env default."""
    return ElevenLabsSpeech(output_format=output_format)
