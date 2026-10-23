"""Worker-side Hermes job metrics (one job = one late follow-up)."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

from vanessa.infrastructure.observability.metrics.metrics_pipeline import registry

_JOB_BUCKETS = (5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0, 3600.0, 6000.0)

hermes_jobs_total = Counter(
    "vanessa_hermes_jobs_total",
    "Hermes worker jobs by outcome",
    # answered | no_answer | unavailable | dropped | merged | failed
    ["outcome"],
    registry=registry,
)
hermes_job_duration_seconds = Histogram(
    "vanessa_hermes_job_duration_seconds",
    "Hermes worker job duration, start to follow-up publish (seconds)",
    buckets=_JOB_BUCKETS,
    registry=registry,
)


def record_hermes_job(outcome: str, seconds: float | None = None) -> None:
    hermes_jobs_total.labels(outcome=outcome).inc()
    if seconds is not None:
        hermes_job_duration_seconds.observe(seconds)
