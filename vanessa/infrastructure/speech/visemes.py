"""JawOpen / Voice from PCM amplitude — presence OSC can import this later."""

from __future__ import annotations

import math
import struct
from collections.abc import Sequence
from dataclasses import dataclass

_INT16_PEAK = 32768.0
_SILENCE_RMS = 0.02
_JAW_GAIN = 4.0
_SAMPLE_WIDTH = 2
_DEFAULT_FRAME_MS = 20


@dataclass(frozen=True, slots=True)
class VisemeFrame:
    t_ms: float
    jaw_open: float
    voice: float


def visemes_from_pcm(
    pcm: bytes,
    sample_rate: int,
    *,
    frame_ms: int = _DEFAULT_FRAME_MS,
) -> list[VisemeFrame]:
    frame_len = _frame_sample_count(sample_rate, frame_ms)
    if frame_len is None:
        return []
    samples = _int16_samples(pcm)
    if not samples:
        return []
    return _frames_from_samples(samples, sample_rate, frame_len)


def _frame_sample_count(sample_rate: int, frame_ms: int) -> int | None:
    if sample_rate <= 0:
        return None
    if frame_ms <= 0:
        return None
    return max(1, sample_rate * frame_ms // 1000)


def _frames_from_samples(
    samples: Sequence[int],
    sample_rate: int,
    frame_len: int,
) -> list[VisemeFrame]:
    frames: list[VisemeFrame] = []
    for start in range(0, len(samples), frame_len):
        chunk = samples[start : start + frame_len]
        t_ms = start * 1000 / sample_rate
        frames.append(_frame_from_samples(chunk, t_ms))
    return frames


def _int16_samples(pcm: bytes) -> tuple[int, ...]:
    usable = len(pcm) - (len(pcm) % _SAMPLE_WIDTH)
    if usable == 0:
        return ()
    return tuple(sample[0] for sample in struct.iter_unpack("<h", pcm[:usable]))


def _rms(samples: Sequence[int]) -> float:
    if not samples:
        return 0.0
    mean_sq = sum(sample * sample for sample in samples) / len(samples)
    return math.sqrt(mean_sq) / _INT16_PEAK


def _frame_from_samples(samples: Sequence[int], t_ms: float) -> VisemeFrame:
    rms = _rms(samples)
    jaw_open = min(1.0, rms * _JAW_GAIN)
    voice = 1.0 if rms >= _SILENCE_RMS else 0.0
    return VisemeFrame(t_ms=t_ms, jaw_open=jaw_open, voice=voice)
