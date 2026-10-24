"""Make a trace value JSON-safe and clip long strings."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

# Image data URLs (vision turns) keep only this head: the bytes are noise.
DATA_URL_HEAD = 48
_SCALARS = (bool, int, float, type(None))


def clip_text(text: str, limit: int) -> str:
    """``text`` up to ``limit`` chars, with a note on how much was cut."""
    if text.startswith("data:") and len(text) > DATA_URL_HEAD:
        return f"{text[:DATA_URL_HEAD]}…[data url, {len(text)} chars]"
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…[+{len(text) - limit} chars]"


def jsonable(value: Any, limit: int) -> Any:
    """A JSON-safe copy of ``value``; every string is clipped to ``limit``."""
    if isinstance(value, str):
        return clip_text(value, limit)
    if isinstance(value, _SCALARS):
        return value
    if isinstance(value, Mapping):
        return {str(key): jsonable(item, limit) for key, item in value.items()}
    return _jsonable_other(value, limit)


def _jsonable_other(value: Any, limit: int) -> Any:
    if isinstance(value, list | tuple | set | frozenset):
        return [jsonable(item, limit) for item in value]
    return jsonable(_plain(value), limit)


def _plain(value: Any) -> Any:
    """Dataclass / pydantic / enum → plain data; anything else → ``str``."""
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    return str(value)
