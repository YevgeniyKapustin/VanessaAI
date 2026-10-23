"""Hermes Agent settings (the owner's PC agent, reached over an SSH tunnel)."""

from __future__ import annotations


class HermesMixin:
    """Agent (health check) and worker (runs) settings for Hermes."""

    hermes_enabled: bool = False
    # Server side of the reverse tunnel, e.g. http://host.docker.internal:8642
    # (append /p/<profile> for profile routing).
    hermes_url: str = ""
    hermes_api_key: str = ""
    # Per HTTP call (health, start, poll); the agent waits only this long.
    hermes_timeout_seconds: float = 5.0
    hermes_poll_seconds: float = 5.0
    # A run still not done after this is stopped and dropped.
    hermes_max_wait_seconds: float = 6000.0
    # Hermes jobs the worker runs at the same time.
    hermes_max_parallel: int = 3
    hermes_query_max_chars: int = 500
    # Largest generated HTML file the worker sends as a document (UTF-8 bytes).
    hermes_file_max_bytes: int = 262_144
