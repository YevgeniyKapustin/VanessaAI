from vanessa.core import SpeechAudio, SpeechSynthesizer
from vanessa.core.protocols import SpeechAudio as ProtocolAudio
from vanessa.core.protocols import SpeechSynthesizer as ProtocolSynth

_PCM_RATE = 24_000


def test_speech_protocol_is_public() -> None:
    assert SpeechAudio is ProtocolAudio
    assert SpeechSynthesizer is ProtocolSynth
    audio = SpeechAudio(pcm=b"\x00\x00", sample_rate=_PCM_RATE)
    assert audio.pcm == b"\x00\x00"
    assert audio.sample_rate == _PCM_RATE
