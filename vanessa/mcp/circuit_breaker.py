"""Fail-fast circuit breaker for external tool calls (MCP servers)."""

from __future__ import annotations

import time


class CircuitBreaker:
    """Trips after N consecutive failures; reopens after a reset timeout.

    States:
      closed    — normal operation, failures counted
      open      — requests rejected immediately (short-circuit)
      half_open — reset timeout elapsed; one probe request is allowed
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        reset_timeout_seconds: float = 30.0,
    ) -> None:
        self._failure_threshold = max(1, failure_threshold)
        self._reset_timeout = max(0.0, reset_timeout_seconds)
        self._failures = 0
        self._open_since: float | None = None

    @property
    def state(self) -> str:
        if self._open_since is None:
            return "closed"
        if time.monotonic() - self._open_since >= self._reset_timeout:
            return "half_open"
        return "open"

    def allow_request(self) -> bool:
        """True if a call may proceed (not in the ``open`` state)."""
        return self.state != "open"

    def record_success(self) -> None:
        self._failures = 0
        self._open_since = None

    def record_failure(self) -> None:
        if self.state == "half_open":
            # The probe failed — trip the breaker again.
            self._failures = 1
            self._open_since = time.monotonic()
            return
        self._failures += 1
        if self._failures >= self._failure_threshold:
            self._open_since = time.monotonic()
