"""Agent-side Hermes metrics: the Retrieve stage health check + task dispatch."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

from vanessa.infrastructure.observability.metrics.metrics_pipeline import (
    registry,
)

hermes_dispatch_total = Counter(
    "vanessa_hermes_dispatch_total",
    "Hermes ask outcomes in the Retrieve stage: asked / offline / error / answered",
    ["status"],
    registry=registry,
)
hermes_health_duration_seconds = Histogram(
    "vanessa_hermes_health_duration_seconds",
    "Hermes /health check latency in the Retrieve stage (seconds)",
    registry=registry,
)


def record_hermes_dispatch(status: str, ms: float) -> None:
    """Record one Hermes ask outcome and the health check latency."""
    hermes_dispatch_total.labels(status=status).inc()
    hermes_health_duration_seconds.observe(ms / 1000.0)


def record_hermes_answered() -> None:
    """Record an ask skipped because a fresh result already answers it."""
    hermes_dispatch_total.labels(status="answered").inc()
