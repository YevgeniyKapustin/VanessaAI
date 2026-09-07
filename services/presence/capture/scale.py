from __future__ import annotations

import io
from collections.abc import Callable

import numpy as np

from services.presence.capture.jpeg_encode import rgb_to_jpeg

try:
    from PIL import Image
except ImportError:
    Image = None

type Shot = tuple[int, int, bytes]
type JpegEncoder = Callable[[Shot], bytes | None]

MAX_LONG_SIDE = 1280
MAX_JPEG_BYTES = 400 * 1024
JPEG_QUALITY = 55
JPEG_QUALITIES = (55, 40, 28, 18)
SHRINK_SIDES = (1280, 960, 720, 480)


def resize_long_side(
    width: int,
    height: int,
    *,
    max_side: int = MAX_LONG_SIDE,
) -> tuple[int, int]:
    long_side = max(width, height)
    if long_side <= max_side:
        return width, height
    scale = max_side / long_side
    return max(1, round(width * scale)), max(1, round(height * scale))


def resize_rgb(
    width: int,
    height: int,
    rgb: bytes,
    new_width: int,
    new_height: int,
) -> bytes:
    if (width, height) == (new_width, new_height):
        return rgb
    src = np.frombuffer(rgb, dtype=np.uint8).reshape(height, width, 3)
    rows = (np.arange(new_height) * height / new_height).astype(int)
    cols = (np.arange(new_width) * width / new_width).astype(int)
    return np.ascontiguousarray(src[rows[:, None], cols]).tobytes()


def scale_shot(shot: Shot, *, max_side: int) -> Shot:
    width, height, rgb = shot
    new_w, new_h = resize_long_side(width, height, max_side=max_side)
    return new_w, new_h, resize_rgb(width, height, rgb, new_w, new_h)


def jpeg_under_cap(
    shot: Shot,
    *,
    encode: Callable[..., bytes | None],
    max_bytes: int = MAX_JPEG_BYTES,
) -> bytes | None:
    for max_side in SHRINK_SIDES:
        scaled = scale_shot(shot, max_side=max_side)
        blob = _first_fitting(scaled, encode=encode, max_bytes=max_bytes)
        if blob is not None:
            return blob
    return None


def _first_fitting(
    shot: Shot,
    *,
    encode: Callable[..., bytes | None],
    max_bytes: int,
) -> bytes | None:
    for quality in JPEG_QUALITIES:
        blob = encode(shot, quality=quality)
        if blob and len(blob) <= max_bytes:
            return blob
    return None


def default_encode(shot: Shot, *, quality: int = JPEG_QUALITY) -> bytes | None:
    blob = _encode_pil(shot, quality=quality)
    if blob is not None:
        return blob
    try:
        return rgb_to_jpeg(shot, quality=quality)
    except (ValueError, OSError):
        return None


def _encode_pil(shot: Shot, *, quality: int) -> bytes | None:
    if Image is None:
        return None
    width, height, rgb = shot
    image = Image.frombytes("RGB", (width, height), rgb)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()
