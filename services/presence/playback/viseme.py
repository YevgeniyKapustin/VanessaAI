from __future__ import annotations

import math
import struct

CHUNK_MS = 20
PCM16_PEAK = 32768.0
VOICE_GATE = 0.02


def pcm16_rms(chunk: bytes) -> float:
    count = len(chunk) // 2
    if count <= 0:
        return 0.0
    samples = struct.unpack(f"<{count}h", chunk[: count * 2])
    acc = sum(sample * sample for sample in samples)
    return math.sqrt(acc / count)


def rms_to_unit(rms: float, *, peak: float = PCM16_PEAK) -> float:
    if peak <= 0 or rms <= 0:
        return 0.0
    return min(1.0, rms / (peak * 0.35))


def chunk_bytes(sample_rate: int, *, chunk_ms: int = CHUNK_MS) -> int:
    raw = sample_rate * 2 * chunk_ms // 1000
    return max(2, raw - (raw % 2))


def iter_pcm_chunks(
    pcm: bytes,
    sample_rate: int,
    *,
    chunk_ms: int = CHUNK_MS,
) -> list[bytes]:
    size = chunk_bytes(sample_rate, chunk_ms=chunk_ms)
    return [pcm[index : index + size] for index in range(0, len(pcm), size)]


def viseme_unit(chunk: bytes) -> float:
    return rms_to_unit(pcm16_rms(chunk))


def voice_from_unit(unit: float) -> float:
    if unit < VOICE_GATE:
        return 0.0
    return unit
