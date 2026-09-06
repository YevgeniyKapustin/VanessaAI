from __future__ import annotations

import time
from collections.abc import Callable
from threading import Lock
from typing import Any

from vanessa.config.settings import settings


class EventWindow:
    """Thread-safe rolling buffer of (timestamp, value) samples.

    Used by the AlertManager to compute error rates and latency percentiles
    over a sliding window without querying Prometheus.
    """

    def __init__(self, window_seconds: float | None = None) -> None:
        self._window = (
            window_seconds
            if window_seconds is not None
            else float(settings.alerting_window_seconds)
        )
        self._lock = Lock()
        self._samples: list[tuple[float, Any]] = []

    def add(self, value: Any, at: float | None = None) -> None:
        now = time.time() if at is None else at
        with self._lock:
            self._samples.append((now, value))
            self._prune(now)

    def _prune(self, now: float) -> None:
        cutoff = now - self._window
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.pop(0)

    def snapshot(self) -> list[Any]:
        with self._lock:
            self._prune(time.time())
            return [value for _, value in self._samples]

    def count(self) -> int:
        return len(self.snapshot())

    def error_rate(self, is_error: Callable[[Any], bool]) -> float:
        samples = self.snapshot()
        if not samples:
            return 0.0
        return sum(1 for value in samples if is_error(value)) / len(samples)

    def percentile(self, percentile: float) -> float | None:
        samples = self.snapshot()
        if not samples:
            return None
        ordered = sorted(samples)
        index = min(len(ordered) - 1, round(percentile / 100.0 * (len(ordered) - 1)))
        return float(ordered[index])

    def clear(self) -> None:
        with self._lock:
            self._samples.clear()


# Sliding-window buffers feeding the AlertManager. Populated from the same
# record_* functions that update the Prometheus counters.
llm_outcomes = EventWindow()
llm_empty_outcomes = EventWindow()
llm_cost_outcomes = EventWindow()
turn_durations = EventWindow()
rag_outcomes = EventWindow()
telegram_outcomes = EventWindow()
telegram_limit_outcomes = EventWindow()

# Activity windows: unique ids over a rolling period. Values are refreshed into
# the active_users / active_sessions gauges on every record and at each scrape
# (see render_metrics) so they decay to 0 once the window empties.
active_users_1h = EventWindow(window_seconds=3600)
active_users_24h = EventWindow(window_seconds=86400)
active_sessions_5m = EventWindow(window_seconds=300)
