from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from services.presence.capture.grab import grab_win32_rgb
from services.presence.capture.jpeg_encode import rgb_to_jpeg
from services.presence.capture.scale import (
    JPEG_QUALITY,
    MAX_JPEG_BYTES,
    MAX_LONG_SIDE,
    Shot,
    default_encode,
    jpeg_under_cap,
    resize_long_side,
)

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

logger = logging.getLogger(__name__)

type Grabber = Callable[[], Shot | None]


def default_grab() -> Shot | None:
    shot = _grab_pil()
    if shot is not None:
        return shot
    return grab_win32_rgb()


def _grab_pil() -> Shot | None:
    if ImageGrab is None:
        return None
    image = ImageGrab.grab().convert("RGB")
    return image.width, image.height, image.tobytes()


async def capture_scene_jpeg(
    *,
    grab: Grabber = default_grab,
    encode: Callable[..., bytes | None] = default_encode,
) -> bytes | None:
    shot = await asyncio.to_thread(grab)
    if shot is None:
        logger.info("presence_scene_skipped")
        return None
    blob = await asyncio.to_thread(jpeg_under_cap, shot, encode=encode)
    if blob is None:
        logger.info("presence_scene_over_cap")
    return blob


__all__ = [
    "JPEG_QUALITY",
    "MAX_JPEG_BYTES",
    "MAX_LONG_SIDE",
    "Shot",
    "capture_scene_jpeg",
    "default_encode",
    "default_grab",
    "jpeg_under_cap",
    "resize_long_side",
    "rgb_to_jpeg",
]
