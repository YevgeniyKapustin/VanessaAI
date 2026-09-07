from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import Structure, byref, create_string_buffer, sizeof, wintypes

import numpy as np

from services.presence.capture.scale import Shot

logger = logging.getLogger(__name__)

SRCCOPY = 0x00CC0020
BITCOUNT_24 = 24


class BitmapInfo(Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]

logger = logging.getLogger(__name__)

SRCCOPY = 0x00CC0020


def bgr_bottom_up_to_rgb(
    width: int,
    height: int,
    pixels: bytes,
    *,
    stride: int | None = None,
) -> bytes:
    row = stride if stride is not None else width * 3
    src = np.frombuffer(pixels, dtype=np.uint8)
    rows = src.reshape(height, row)[:, : width * 3]
    bgr = rows.reshape(height, width, 3)
    rgb = bgr[::-1, :, ::-1]
    return np.ascontiguousarray(rgb).tobytes()


def grab_win32_rgb() -> Shot | None:
    if sys.platform != "win32":
        return None
    try:
        return _capture_desktop()
    except (OSError, AttributeError, ValueError):
        logger.warning("presence_screenshot_failed", exc_info=True)
        return None


def _capture_desktop() -> Shot:
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    width = int(user32.GetSystemMetrics(0))
    height = int(user32.GetSystemMetrics(1))
    stride = (width * 3 + 3) & ~3
    hdc = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, width, height)
    gdi32.SelectObject(mem, bmp)
    gdi32.BitBlt(mem, 0, 0, width, height, hdc, 0, 0, SRCCOPY)
    header = _bitmap_info(width, height)
    pixels = create_string_buffer(stride * height)
    gdi32.GetDIBits(hdc, bmp, 0, height, pixels, byref(header), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(0, hdc)
    rgb = bgr_bottom_up_to_rgb(width, height, pixels.raw, stride=stride)
    return width, height, rgb


def _bitmap_info(width: int, height: int) -> BitmapInfo:
    info = BitmapInfo()
    info.biSize = sizeof(BitmapInfo)
    info.biWidth = width
    info.biHeight = height
    info.biPlanes = 1
    info.biBitCount = BITCOUNT_24
    return info
