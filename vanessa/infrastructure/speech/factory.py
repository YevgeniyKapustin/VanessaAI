from vanessa.infrastructure.speech.elevenlabs import ElevenLabsSpeech


def create_speech_synthesizer() -> ElevenLabsSpeech:
    return ElevenLabsSpeech()
