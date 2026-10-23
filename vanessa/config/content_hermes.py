"""Hermes follow-up prompts: ``config/behavior/hermes/followup.yaml``.

Kept apart from ``AppContent``: only the worker needs it, and only when
Hermes is enabled.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from vanessa.config.content import resolve_content_source

HERMES_FOLLOWUP_FILE = Path("hermes", "followup.yaml")


class HermesContent(BaseModel):
    run_instructions: str
    data_rules: str
    answered_task: str
    undelivered_task: str
    undelivered_fallback: str = Field(min_length=1)
    max_tokens: int = Field(default=1024, ge=64, le=4096)


def load_hermes_content(path: Path) -> HermesContent:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return HermesContent.model_validate(raw)


@lru_cache
def get_hermes_content() -> HermesContent:
    """Load the follow-up prompts. Fails loudly when the file is missing."""
    source = resolve_content_source()
    return load_hermes_content(source / HERMES_FOLLOWUP_FILE)


__all__ = [
    "HERMES_FOLLOWUP_FILE",
    "HermesContent",
    "get_hermes_content",
    "load_hermes_content",
]
