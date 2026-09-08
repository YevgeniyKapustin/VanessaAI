"""Locate YAML under ``config/``: cwd first, then the repo root."""

from __future__ import annotations

from pathlib import Path

from vanessa.config.settings import settings


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_config_path(configured: str | Path) -> Path:
    path = Path(configured)
    if path.exists():
        return path
    if path.is_absolute():
        return path
    fallback = repo_root() / path
    if fallback.exists():
        return fallback
    return path


def resolve_settings_path(override: str, *parts: str) -> Path:
    """Prefer an explicit env path; otherwise ``{config_root}/parts``."""
    configured = override.strip() or str(Path(settings.config_root, *parts))
    return resolve_config_path(configured)
