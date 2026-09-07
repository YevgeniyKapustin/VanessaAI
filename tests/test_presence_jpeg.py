from __future__ import annotations

import os

from services.presence.capture import capture_scene_jpeg, default_grab
from services.presence.capture.grab import bgr_bottom_up_to_rgb
from services.presence.capture.jpeg_encode import rgb_to_jpeg
from services.presence.capture.jpeg_tables import AC_LUMA_BITS, AC_LUMA_VAL
from services.presence.capture.scale import (
    MAX_JPEG_BYTES,
    jpeg_under_cap,
    resize_long_side,
    resize_rgb,
)
from services.presence.turn_request import scene_image_from_jpeg


def _solid_rgb(width: int, height: int, color: bytes = b"\xff\x00\x00") -> bytes:
    return color * (width * height)


def test_huffman_table_lengths_match() -> None:
    assert sum(AC_LUMA_BITS) == len(AC_LUMA_VAL)


def test_resize_long_side_caps_1280() -> None:
    assert resize_long_side(1920, 1080) == (1280, 720)
    assert resize_long_side(800, 600) == (800, 600)


MAX_FAKE_BYTES = 50_000
RGB_PIXELS = 12


def test_jpeg_under_cap_shrinks_fake_encoder() -> None:
    def encode(shot, *, quality: int) -> bytes:
        width, height, _rgb = shot
        size = max(80, (width * height * quality) // 50)
        return b"\xff\xd8" + (b"x" * size) + b"\xff\xd9"

    width, height = 2000, 1000
    huge = (width, height, _solid_rgb(width, height))
    blob = jpeg_under_cap(huge, encode=encode, max_bytes=MAX_FAKE_BYTES)
    assert blob is not None
    assert blob.startswith(b"\xff\xd8")
    assert len(blob) <= MAX_FAKE_BYTES


def test_jpeg_under_cap_returns_none_when_still_too_big() -> None:
    def encode(_shot, *, quality: int) -> bytes:
        del quality
        return b"\xff\xd8" + (b"y" * (MAX_JPEG_BYTES + 10)) + b"\xff\xd9"

    blob = jpeg_under_cap((16, 16, _solid_rgb(16, 16)), encode=encode)
    assert blob is None


def test_rgb_to_jpeg_magic_and_under_default_cap() -> None:
    width, height = 32, 24
    jpeg = rgb_to_jpeg((width, height, _solid_rgb(width, height)), quality=55)
    assert jpeg.startswith(b"\xff\xd8")
    assert jpeg.endswith(b"\xff\xd9")
    assert len(jpeg) <= MAX_JPEG_BYTES


def test_scene_image_has_no_telegram_file_id() -> None:
    image = scene_image_from_jpeg(b"\xff\xd8\xff\xd9")
    assert image is not None
    assert image.telegram_file_id is None
    assert image.mime_type == "image/jpeg"
    assert image.data_url.startswith("data:image/jpeg;base64,")
    assert scene_image_from_jpeg(None) is None


def test_bgr_bottom_up_to_rgb() -> None:
    # 2x2, stride packed: bottom row BGR then top row.
    pixels = bytes(
        [
            0, 0, 255,  # bottom-left red in BGR? B=0 G=0 R=255 → red
            0, 255, 0,  # bottom-right green BGR
            255, 0, 0,  # top-left blue
            255, 255, 255,  # top-right white
        ]
    )
    rgb = bgr_bottom_up_to_rgb(2, 2, pixels)
    assert rgb[0:3] == bytes([0, 0, 255])  # top-left becomes blue RGB
    assert len(rgb) == RGB_PIXELS


def test_resize_rgb_nearest() -> None:
    src = _solid_rgb(2, 2, b"\x10\x20\x30")
    out = resize_rgb(2, 2, src, 1, 1)
    assert out == b"\x10\x20\x30"


async def test_capture_scene_jpeg_none_on_failed_grab() -> None:
    blob = await capture_scene_jpeg(grab=lambda: None)
    assert blob is None


def test_default_grab_does_not_raise() -> None:
    shot = default_grab()
    assert shot is None or isinstance(shot, tuple)


async def test_capture_scene_over_cap() -> None:
    def grab():
        return 8, 8, _solid_rgb(8, 8)

    def encode(_shot, *, quality: int) -> bytes:
        del quality
        return b"\xff\xd8" + (b"z" * (MAX_JPEG_BYTES + 8)) + b"\xff\xd9"

    blob = await capture_scene_jpeg(grab=grab, encode=encode)
    assert blob is None


def test_noisy_jpeg_encodes() -> None:
    noise = os.urandom(64 * 64 * 3)
    jpeg = rgb_to_jpeg((64, 64, noise), quality=90)
    assert jpeg.startswith(b"\xff\xd8")
