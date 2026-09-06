from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values

from vanessa.config.env_overlay_filters import (
    ANTHROPIC_PREFIX,
    PLACEHOLDER_MARKERS,
    SKIP_KEYS,
    is_placeholder_value,
    keep_anthropic_provider,
    matches_default_value,
    skip_anthropic_key,
    skip_overlay_key,
    windows_compose_file,
)

LOCAL_PROFILE: dict[str, str] = {
    "WEB_SEARCH_ENABLED": "true",
    "LANGFUSE_ENABLED": "false",
    "WORKER_ENABLED": "true",
}

__all__ = [
    "ANTHROPIC_PREFIX",
    "LOCAL_PROFILE",
    "PLACEHOLDER_MARKERS",
    "SKIP_KEYS",
    "build_local_overlay",
    "format_env_value",
    "load_env_values",
    "prepare_local_overlay",
    "render_overlay",
]


def _stripped_env_value(
    key: str | None,
    value: str | None,
) -> tuple[str, str] | None:
    if not key or value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return key, stripped


def load_env_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    loaded: dict[str, str] = {}
    for key, value in dotenv_values(path).items():
        entry = _stripped_env_value(key, value)
        if entry is None:
            continue
        loaded[entry[0]] = entry[1]
    return loaded


def _keep_legacy_overlay_value(
    key: str,
    value: str,
    defaults: Mapping[str, str],
    *,
    keep_anthropic: bool,
) -> bool:
    if skip_overlay_key(key):
        return False
    if is_placeholder_value(value):
        return False
    if skip_anthropic_key(key, keep_anthropic=keep_anthropic):
        return False
    return not matches_default_value(key, value, defaults)


def _legacy_overlay_values(
    defaults: Mapping[str, str],
    legacy: Mapping[str, str],
    *,
    keep_anthropic: bool,
) -> dict[str, str]:
    overlay: dict[str, str] = dict(LOCAL_PROFILE)
    for key, value in legacy.items():
        if not _keep_legacy_overlay_value(
            key, value, defaults, keep_anthropic=keep_anthropic
        ):
            continue
        overlay[key] = value
    return overlay


def build_local_overlay(
    defaults: Mapping[str, str],
    legacy: Mapping[str, str],
    *,
    windows: bool | None = None,
) -> dict[str, str]:
    if windows is None:
        windows = os.name == "nt"
    overlay = _legacy_overlay_values(
        defaults,
        legacy,
        keep_anthropic=keep_anthropic_provider(legacy),
    )
    compose = windows_compose_file(defaults, overlay, windows=windows)
    if compose is not None:
        overlay["COMPOSE_FILE"] = compose
    return overlay


def format_env_value(value: str) -> str:
    if any(char in value for char in ' \t#"\''):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def render_overlay(values: Mapping[str, str]) -> str:
    lines = [
        "# Generated overlay. Do not commit. Loaded after .env.defaults.",
        "",
    ]
    for key in sorted(values):
        lines.append(f"{key}={format_env_value(values[key])}")
    lines.append("")
    return "\n".join(lines)


def prepare_local_overlay(
    root: Path,
    *,
    source: Path | None = None,
    destination: Path | None = None,
    windows: bool | None = None,
) -> tuple[dict[str, str], Path]:
    defaults_path = root / ".env.defaults"
    if not defaults_path.is_file():
        raise FileNotFoundError(f"missing {defaults_path}")
    source_path = source or root / ".env"
    if not source_path.is_file():
        raise FileNotFoundError(
            f"no source env at {source_path}; pass --from PATH"
        )
    dest = destination or root / ".env.local"
    overlay = build_local_overlay(
        load_env_values(defaults_path),
        load_env_values(source_path),
        windows=windows,
    )
    return overlay, dest
