import struct

from vanessa.infrastructure.speech.pcm import pcm_to_wav, sample_rate_from_output_format

_RATE_16K = 16_000
_RATE_24K = 24_000
_RATE_44K = 44_100


def test_sample_rate_from_pcm_format() -> None:
    assert sample_rate_from_output_format("pcm_16000") == _RATE_16K
    assert sample_rate_from_output_format("pcm_24000") == _RATE_24K
    assert sample_rate_from_output_format("pcm_44100") == _RATE_44K


def test_sample_rate_unknown_format_falls_back() -> None:
    assert sample_rate_from_output_format("mp3_44100_128") == _RATE_24K
    assert sample_rate_from_output_format("pcm_") == _RATE_24K


def test_pcm_to_wav_wraps_riff_header() -> None:
    pcm = struct.pack("<hh", 1, -1)
    wav = pcm_to_wav(pcm, _RATE_16K)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert wav[-len(pcm) :] == pcm
    rate = struct.unpack_from("<I", wav, 24)[0]
    assert rate == _RATE_16K


def test_pcm_to_wav_zero_rate_falls_back() -> None:
    wav = pcm_to_wav(b"\x00\x00", 0)
    rate = struct.unpack_from("<I", wav, 24)[0]
    assert rate == _RATE_24K
