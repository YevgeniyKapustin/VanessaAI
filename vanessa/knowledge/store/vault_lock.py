"""Shared vault lock and state filename (imported by stores and the facade)."""

from __future__ import annotations

import asyncio

STATE_FILENAME = ".state.yaml"
VAULT_LOCK = asyncio.Lock()
