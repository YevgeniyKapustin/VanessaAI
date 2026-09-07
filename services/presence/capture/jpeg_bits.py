from __future__ import annotations

BYTE_BITS = 8
STUFF_MARKER = 0xFF
BYTE_MASK = 0xFF


class BitWriter:
    def __init__(self) -> None:
        self._buf = bytearray()
        self._acc = 0
        self._n = 0

    def write(self, bits: int, length: int) -> None:
        if length <= 0:
            return
        self._acc = (self._acc << length) | (bits & ((1 << length) - 1))
        self._n += length
        while self._n >= BYTE_BITS:
            self._n -= BYTE_BITS
            byte = (self._acc >> self._n) & BYTE_MASK
            self._buf.append(byte)
            if byte == STUFF_MARKER:
                self._buf.append(0x00)
            self._acc &= (1 << self._n) - 1

    def write_huffman(self, table: dict[int, tuple[int, int]], symbol: int) -> None:
        code, length = table[symbol]
        self.write(code, length)

    def flush(self) -> bytes:
        if self._n:
            self.write(0, BYTE_BITS - self._n)
        return bytes(self._buf)
