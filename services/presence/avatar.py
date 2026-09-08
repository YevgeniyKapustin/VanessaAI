from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from vanessa.config.paths import resolve_settings_path
from vanessa.config.settings import settings


class OscSection(BaseModel):
    host: str = "127.0.0.1"
    port: int = 9000
    listen_port: int = 9001


class ParameterNames(BaseModel):
    jaw_open: str = "JawOpen"
    voice: str = "Voice"
    breath: str = "Breath"
    look_horizontal: str = "LookHorizontal"


class IdleSection(BaseModel):
    enabled: bool = True
    breath_period_seconds: float = 4.0
    look_period_seconds: float = 7.0
    look_amplitude: float = 0.12


class Gesture(BaseModel):
    parameter: str
    value: float = 1.0
    hold_seconds: float = 1.0


class AvatarConfig(BaseModel):
    speaker_name: str = "You"
    osc: OscSection = Field(default_factory=OscSection)
    parameters: ParameterNames = Field(default_factory=ParameterNames)
    idle: IdleSection = Field(default_factory=IdleSection)
    gestures: dict[str, Gesture] = Field(default_factory=dict)
    emotion_map: dict[str, str] = Field(default_factory=dict)


def resolve_avatar_path(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    env = os.environ.get("PRESENCE_AVATAR_PATH", "").strip()
    if env:
        return Path(env)
    return resolve_settings_path(
        settings.presence_avatar_path, "presence", "avatar.yaml"
    )


def load_avatar(path: Path | None = None) -> AvatarConfig:
    source = resolve_avatar_path(path)
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return AvatarConfig()
    return AvatarConfig.model_validate(data)
