"""Telegram ``speech`` flag. Prefer channel YAML; otherwise stay off."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from vanessa.config.channels import load_channel_profile

logger = logging.getLogger(__name__)


def resolve_telegram_speech_enabled(
    *,
    default: bool = False,
    channels_path: Path | None = None,
) -> bool:
    if channels_path is not None:
        return _flag_or_default(channels_path, default=default)
    try:
        return load_channel_profile("telegram").speech
    except (OSError, ValueError) as exc:
        logger.warning("telegram_speech_profile_unreadable error=%s", exc)
        return default


def _flag_or_default(path: Path, *, default: bool) -> bool:
    if not path.is_file():
        return default
    flag = _speech_flag_from_yaml(path)
    if flag is None:
        return default
    return flag


def _speech_flag_from_yaml(path: Path) -> bool | None:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("telegram_speech_yaml_unreadable path=%s error=%s", path, exc)
        return None
    if not isinstance(loaded, dict) or "speech" not in loaded:
        return None
    return bool(loaded["speech"])
