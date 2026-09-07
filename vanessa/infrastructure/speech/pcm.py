"""PCM helpers shared by Telegram voice wrap and presence visemes."""

from __future__ import annotations

import struct

_DEFAULT_PCM_RATE = 24_000
_WAV_CHANNELS = 1
_WAV_SAMPLE_WIDTH = 2
_PCM_PREFIX = "pcm_"


def sample_rate_from_output_format(output_format: str) -> int:
    if not output_format.startswith(_PCM_PREFIX):
        return _DEFAULT_PCM_RATE
    suffix = output_format.removeprefix(_PCM_PREFIX)
    if not suffix.isdigit():
        return _DEFAULT_PCM_RATE
    return int(suffix)


def pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap 16-bit mono PCM in a RIFF/WAVE container (no extra codecs)."""
    rate = sample_rate if sample_rate > 0 else _DEFAULT_PCM_RATE
    data_size = len(pcm)
    byte_rate = rate * _WAV_CHANNELS * _WAV_SAMPLE_WIDTH
    block_align = _WAV_CHANNELS * _WAV_SAMPLE_WIDTH
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        _WAV_CHANNELS,
        rate,
        byte_rate,
        block_align,
        _WAV_SAMPLE_WIDTH * 8,
        b"data",
        data_size,
    )
    return header + pcm
