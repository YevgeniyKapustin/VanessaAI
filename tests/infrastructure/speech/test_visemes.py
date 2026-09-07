import math
import struct

from vanessa.infrastructure.speech.visemes import _rms, visemes_from_pcm

_RATE = 24_000
_FRAME_MS = 20
_FRAME_SAMPLES = _RATE * _FRAME_MS // 1000


def _pcm(samples: list[int]) -> bytes:
    return b"".join(struct.pack("<h", sample) for sample in samples)


def test_visemes_empty_or_invalid() -> None:
    assert visemes_from_pcm(b"", _RATE) == []
    assert visemes_from_pcm(_pcm([1]), 0) == []
    assert visemes_from_pcm(_pcm([1]), _RATE, frame_ms=0) == []
    assert visemes_from_pcm(b"\x00", _RATE) == []


def test_visemes_silence_closes_jaw() -> None:
    pcm = _pcm([0] * _FRAME_SAMPLES)
    frames = visemes_from_pcm(pcm, _RATE, frame_ms=_FRAME_MS)
    assert len(frames) == 1
    assert frames[0].t_ms == 0.0
    assert frames[0].jaw_open == 0.0
    assert frames[0].voice == 0.0


def test_visemes_loud_opens_jaw_and_voice() -> None:
    pcm = _pcm([20_000] * _FRAME_SAMPLES)
    frames = visemes_from_pcm(pcm, _RATE, frame_ms=_FRAME_MS)
    assert len(frames) == 1
    assert frames[0].voice == 1.0
    assert frames[0].jaw_open == 1.0


def test_visemes_frame_times_follow_sample_rate() -> None:
    pcm = _pcm([0] * (_FRAME_SAMPLES * 2))
    frames = visemes_from_pcm(pcm, _RATE, frame_ms=_FRAME_MS)
    expected_frames = 2
    assert len(frames) == expected_frames
    assert frames[0].t_ms == 0.0
    assert math.isclose(frames[1].t_ms, float(_FRAME_MS))


def test_rms_empty_samples_is_zero() -> None:
    assert _rms(()) == 0.0
