from __future__ import annotations

import asyncio
import struct
import sys
import tempfile
from pathlib import Path
from typing import Protocol

if sys.platform == "win32":
    import winsound
else:
    winsound = None


class AudioPlayer(Protocol):
    async def play(self, pcm: bytes, sample_rate: int) -> None: ...


class NullPlayer:
    async def play(self, pcm: bytes, sample_rate: int) -> None:
        del pcm, sample_rate


class RecordingPlayer:
    def __init__(self) -> None:
        self.played: list[tuple[bytes, int]] = []

    async def play(self, pcm: bytes, sample_rate: int) -> None:
        self.played.append((pcm, sample_rate))


def pcm16_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    data_size = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        sample_rate * 2,
        2,
        16,
        b"data",
        data_size,
    )
    return header + pcm


def play_wav_bytes(wav: bytes) -> None:
    if winsound is None or not wav:
        return

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        handle.write(wav)
        path = handle.name
    try:
        winsound.PlaySound(path, winsound.SND_FILENAME)
    finally:
        Path(path).unlink(missing_ok=True)


class DefaultPlayer:
    async def play(self, pcm: bytes, sample_rate: int) -> None:
        if not pcm:
            return
        wav = pcm16_to_wav(pcm, sample_rate)
        await asyncio.to_thread(play_wav_bytes, wav)
