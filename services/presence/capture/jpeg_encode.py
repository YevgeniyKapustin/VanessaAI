from __future__ import annotations

import numpy as np

from services.presence.capture.jpeg_bits import BitWriter
from services.presence.capture.jpeg_tables import (
    AC_LUMA,
    AC_LUMA_BITS,
    AC_LUMA_VAL,
    CHROMA_Q,
    DC_LUMA,
    DC_LUMA_BITS,
    DC_LUMA_VAL,
    LUMA_Q,
    ZIGZAG,
    scale_quant,
)

type Shot = tuple[int, int, bytes]


def rgb_to_jpeg(shot: Shot, *, quality: int = 55) -> bytes:
    width, height, rgb = shot
    ycbcr = _ycbcr(width, height, rgb)
    luma_q = scale_quant(LUMA_Q, quality)
    chroma_q = scale_quant(CHROMA_Q, quality)
    scan = _encode_scan(ycbcr, luma_q, chroma_q)
    return _markers(width, height, luma_q, chroma_q) + scan + b"\xff\xd9"


def _ycbcr(width: int, height: int, rgb: bytes) -> np.ndarray:
    pad_w = (width + 7) & ~7
    pad_h = (height + 7) & ~7
    src = np.frombuffer(rgb, dtype=np.uint8).reshape(height, width, 3)
    canvas = np.zeros((pad_h, pad_w, 3), dtype=np.float32)
    canvas[:height, :width] = src
    red, green, blue = canvas[:, :, 0], canvas[:, :, 1], canvas[:, :, 2]
    y_ch = 0.299 * red + 0.587 * green + 0.114 * blue
    cb = 128.0 - 0.168736 * red - 0.331264 * green + 0.5 * blue
    cr = 128.0 + 0.5 * red - 0.418688 * green - 0.081312 * blue
    return np.stack((y_ch, cb, cr), axis=2)


def _cos_matrix() -> np.ndarray:
    index = np.arange(8)
    k = index.reshape(8, 1)
    alpha = np.sqrt(2.0 / 8.0) * np.ones((8, 8))
    alpha[0, :] = np.sqrt(1.0 / 8.0)
    return alpha * np.cos(np.pi * (2 * index + 1) * k / 16.0)


def _encode_scan(
    ycbcr: np.ndarray,
    luma_q: list[int],
    chroma_q: list[int],
) -> bytes:
    height, width, _ = ycbcr.shape
    cosine = _cos_matrix()
    writer = BitWriter()
    prev_dc = [0, 0, 0]
    quant = (luma_q, chroma_q, chroma_q)
    for row in range(0, height, 8):
        for col in range(0, width, 8):
            _encode_mcu(
                ycbcr[row : row + 8, col : col + 8],
                cosine,
                quant,
                prev_dc,
                writer,
            )
    return writer.flush()


def _encode_mcu(
    mcu: np.ndarray,
    cosine: np.ndarray,
    quant: tuple[list[int], list[int], list[int]],
    prev_dc: list[int],
    writer: BitWriter,
) -> None:
    for channel in range(3):
        block = mcu[:, :, channel] - 128.0
        dct = cosine @ block @ cosine.T
        qtable = np.array(quant[channel], dtype=np.float32).reshape(8, 8)
        coeffs = np.clip(np.rint(dct / qtable), -1023, 1023).astype(np.int32)
        zz = [int(coeffs.reshape(64)[index]) for index in ZIGZAG]
        _write_block(writer, zz, prev_dc, channel)


def _write_block(
    writer: BitWriter,
    zigzag: list[int],
    prev_dc: list[int],
    channel: int,
) -> None:
    dc = zigzag[0]
    diff = dc - prev_dc[channel]
    prev_dc[channel] = dc
    _write_dc(writer, diff)
    _write_ac(writer, zigzag[1:])


def _amp(value: int) -> tuple[int, int]:
    if value == 0:
        return 0, 0
    cat = abs(value).bit_length()
    bits = value if value > 0 else value + (1 << cat) - 1
    return cat, bits


def _write_dc(writer: BitWriter, diff: int) -> None:
    cat, bits = _amp(diff)
    writer.write_huffman(DC_LUMA, cat)
    writer.write(bits, cat)


def _write_ac(writer: BitWriter, rest: list[int]) -> None:
    zeros = 0
    for coef in rest:
        if coef == 0:
            zeros += 1
            continue
        zeros = _flush_zeros(writer, zeros)
        cat, bits = _amp(coef)
        writer.write_huffman(AC_LUMA, (zeros << 4) | cat)
        writer.write(bits, cat)
        zeros = 0
    if zeros:
        writer.write_huffman(AC_LUMA, 0)


ZRL_RUN = 16
ZRL_SYMBOL = 0xF0


def _flush_zeros(writer: BitWriter, zeros: int) -> int:
    while zeros >= ZRL_RUN:
        writer.write_huffman(AC_LUMA, ZRL_SYMBOL)
        zeros -= ZRL_RUN
    return zeros


def _markers(
    width: int,
    height: int,
    luma_q: list[int],
    chroma_q: list[int],
) -> bytes:
    return b"".join(
        (
            b"\xff\xd8",
            _app0(),
            _dqt(0, luma_q),
            _dqt(1, chroma_q),
            _sof(width, height),
            _dht(0, 0, DC_LUMA_BITS, DC_LUMA_VAL),
            _dht(1, 0, AC_LUMA_BITS, AC_LUMA_VAL),
            _sos(),
        )
    )


def _app0() -> bytes:
    return b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"


def _dqt(ident: int, table: list[int]) -> bytes:
    zigzagged = bytes(table[index] for index in ZIGZAG)
    body = bytes([ident]) + zigzagged
    return b"\xff\xdb" + (len(body) + 2).to_bytes(2, "big") + body


def _sof(width: int, height: int) -> bytes:
    # 8-bit, 3 components: Y uses Q0, Cb/Cr use Q1; 1x1 sampling.
    comps = bytes([1, 0x11, 0, 2, 0x11, 1, 3, 0x11, 1])
    body = bytes([8]) + height.to_bytes(2, "big") + width.to_bytes(2, "big")
    body += bytes([3]) + comps
    return b"\xff\xc0" + (len(body) + 2).to_bytes(2, "big") + body


def _dht(
    table_class: int,
    ident: int,
    bits: tuple[int, ...],
    values: bytes,
) -> bytes:
    body = bytes([(table_class << 4) | ident]) + bytes(bits) + values
    return b"\xff\xc4" + (len(body) + 2).to_bytes(2, "big") + body


def _sos() -> bytes:
    comps = bytes([3, 1, 0x00, 2, 0x00, 3, 0x00, 0, 63, 0])
    return b"\xff\xda" + (len(comps) + 2).to_bytes(2, "big") + comps
