from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values

SKIP_KEYS = frozenset({"VISION_PHOTO_PLACEHOLDER"})
ANTHROPIC_PREFIX = "ANTHROPIC_"
PLACEHOLDER_MARKERS = (
    "your_",
    "pk-lf-...",
    "sk-lf-...",
    "change-me",
)

LOCAL_PROFILE: dict[str, str] = {
    "WEB_SEARCH_ENABLED": "true",
    "LANGFUSE_ENABLED": "false",
    "WORKER_ENABLED": "true",
}


def load_env_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    loaded: dict[str, str] = {}
    for key, value in dotenv_values(path).items():
        if not key or value is None:
            continue
        stripped = value.strip()
        if stripped:
            loaded[key] = stripped
    return loaded


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def _keep_anthropic(legacy: Mapping[str, str]) -> bool:
    provider = legacy.get("LLM_PROVIDER", "deepseek").strip().lower()
    return provider == "claude"


def build_local_overlay(
    defaults: Mapping[str, str],
    legacy: Mapping[str, str],
    *,
    windows: bool | None = None,
) -> dict[str, str]:
    keep_anthropic = _keep_anthropic(legacy)
    overlay: dict[str, str] = dict(LOCAL_PROFILE)
    for key, value in legacy.items():
        if key in SKIP_KEYS or _is_placeholder(value):
            continue
        if key.startswith(ANTHROPIC_PREFIX) and not keep_anthropic:
            continue
        default = defaults.get(key)
        if default is not None and default == value:
            continue
        overlay[key] = value
    if windows is None:
        windows = os.name == "nt"
    if windows and "COMPOSE_FILE" not in overlay:
        compose = defaults.get("COMPOSE_FILE", "")
        if compose and ":" in compose and ";" not in compose:
            overlay["COMPOSE_FILE"] = compose.replace(":", ";")
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
