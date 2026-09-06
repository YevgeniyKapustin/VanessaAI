from __future__ import annotations

from collections.abc import Mapping

SKIP_KEYS = frozenset({"VISION_PHOTO_PLACEHOLDER"})
ANTHROPIC_PREFIX = "ANTHROPIC_"
PLACEHOLDER_MARKERS = (
    "your_",
    "pk-lf-...",
    "sk-lf-...",
    "change-me",
)


def skip_overlay_key(key: str) -> bool:
    return key in SKIP_KEYS


def is_placeholder_value(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def keep_anthropic_provider(legacy: Mapping[str, str]) -> bool:
    provider = legacy.get("LLM_PROVIDER", "deepseek").strip().lower()
    return provider == "claude"


def skip_anthropic_key(key: str, *, keep_anthropic: bool) -> bool:
    return key.startswith(ANTHROPIC_PREFIX) and not keep_anthropic


def matches_default_value(
    key: str,
    value: str,
    defaults: Mapping[str, str],
) -> bool:
    default = defaults.get(key)
    return default is not None and default == value


def _windows_compose_raw(
    defaults: Mapping[str, str],
    overlay: Mapping[str, str],
    *,
    windows: bool,
) -> str:
    if not windows:
        return ""
    if "COMPOSE_FILE" in overlay:
        return ""
    return defaults.get("COMPOSE_FILE", "")


def windows_compose_file(
    defaults: Mapping[str, str],
    overlay: Mapping[str, str],
    *,
    windows: bool,
) -> str | None:
    compose = _windows_compose_raw(defaults, overlay, windows=windows)
    if not compose:
        return None
    if ":" not in compose:
        return None
    if ";" in compose:
        return None
    return compose.replace(":", ";")
