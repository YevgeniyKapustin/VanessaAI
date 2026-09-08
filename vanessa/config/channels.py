from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, field_validator

from vanessa.config.paths import resolve_settings_path
from vanessa.config.settings import settings

ChannelName = Literal["telegram", "vrchat"]
AddressingMode = Literal["telegram", "addressed"]
ListenWindowMode = Literal["current", "on"]


class ChannelProfile(BaseModel):
    """Per-turn adapter flags. Loaded from ``config/channels/{channel}.yaml``."""

    channel: ChannelName = "telegram"
    stickers: bool = True
    photos: bool = True
    split_messages: bool = True
    scene: bool = False
    speech: bool = False
    listen_window: ListenWindowMode = "current"
    addressing: AddressingMode = "telegram"
    prompt_addendum: str = ""

    @field_validator("listen_window", mode="before")
    @classmethod
    def _yaml_on_is_listen_window(cls, value: object) -> object:
        # YAML 1.1 parses bare `on` as boolean True.
        if value is True:
            return "on"
        if value is False:
            return "current"
        return value


def resolve_channels_dir() -> Path:
    return resolve_settings_path(settings.channels_config_path, "channels")


def _canonical_channel(channel: str | None) -> ChannelName:
    if channel == "vrchat":
        return "vrchat"
    return "telegram"


@lru_cache
def _load_channel_file(name: ChannelName) -> ChannelProfile:
    path = resolve_channels_dir() / f"{name}.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raw = {}
    raw.setdefault("channel", name)
    return ChannelProfile.model_validate(raw)


def load_channel_profile(channel: str | None = None) -> ChannelProfile:
    return _load_channel_file(_canonical_channel(channel))


__all__ = [
    "AddressingMode",
    "ChannelName",
    "ChannelProfile",
    "ListenWindowMode",
    "load_channel_profile",
    "resolve_channels_dir",
]
