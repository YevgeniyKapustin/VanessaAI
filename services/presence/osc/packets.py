from __future__ import annotations

import struct
from collections.abc import Sequence


def pad4(data: bytes) -> bytes:
    extra = (-len(data)) % 4
    return data + (b"\x00" * extra)


def encode_osc(address: str, *values: object) -> bytes:
    tags = [","]
    args = bytearray()
    for value in values:
        tag, encoded = encode_value(value)
        tags.append(tag)
        args.extend(encoded)
    return b"".join(
        (
            pad4(address.encode("utf-8") + b"\x00"),
            pad4("".join(tags).encode("ascii") + b"\x00"),
            bytes(args),
        )
    )


def encode_value(value: object) -> tuple[str, bytes]:
    numeric = _encode_numeric(value)
    if numeric is not None:
        return numeric
    if isinstance(value, str):
        return "s", pad4(value.encode("utf-8") + b"\x00")
    raise TypeError(f"unsupported OSC type: {type(value)!r}")


def _encode_numeric(value: object) -> tuple[str, bytes] | None:
    if isinstance(value, bool):
        return ("T" if value else "F"), b""
    if isinstance(value, int):
        return "i", struct.pack(">i", value)
    if isinstance(value, float):
        return "f", struct.pack(">f", value)
    return None


def decode_osc(packet: bytes) -> tuple[str, tuple[object, ...]] | None:
    if not packet or packet[0:1] != b"/":
        return None
    address, rest = _read_padded_string(packet)
    if not rest or rest[0:1] != b",":
        return address, ()
    tags, body = _read_padded_string(rest)
    values, _ = _read_tagged(tags[1:], body)
    return address, tuple(values)


def _read_padded_string(data: bytes) -> tuple[str, bytes]:
    end = data.find(b"\x00")
    if end < 0:
        return data.decode("utf-8", errors="replace"), b""
    text = data[:end].decode("utf-8", errors="replace")
    padded = (end + 4) & ~3
    return text, data[padded:]


def _read_tagged(tags: str, body: bytes) -> tuple[list[object], bytes]:
    values: list[object] = []
    rest = body
    for tag in tags:
        value, rest = _read_tag(tag, rest)
        values.append(value)
    return values, rest


def _read_tag(tag: str, body: bytes) -> tuple[object, bytes]:
    reader = _TAG_READERS.get(tag)
    if reader is None:
        return tag, body
    return reader(body)


def _read_int(body: bytes) -> tuple[object, bytes]:
    return struct.unpack(">i", body[:4])[0], body[4:]


def _read_float(body: bytes) -> tuple[object, bytes]:
    return struct.unpack(">f", body[:4])[0], body[4:]


def _read_true(body: bytes) -> tuple[object, bytes]:
    return True, body


def _read_false(body: bytes) -> tuple[object, bytes]:
    return False, body


_TAG_READERS = {
    "T": _read_true,
    "F": _read_false,
    "i": _read_int,
    "f": _read_float,
    "s": _read_padded_string,
}


def decode_values(packet: bytes) -> Sequence[object]:
    parsed = decode_osc(packet)
    if parsed is None:
        return ()
    return parsed[1]
