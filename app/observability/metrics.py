from __future__ import annotations

import time
from threading import Lock
from typing import Any, Callable, Mapping

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from app.config.settings import settings

# Dedicated registry so the app and its tests never collide with the global
# default registry (which other libraries may populate).
registry = CollectorRegistry(auto_describe=False)


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
        index = min(len(ordered) - 1, int(round(percentile / 100.0 * (len(ordered) - 1))))
        return float(ordered[index])

    def clear(self) -> None:
        with self._lock:
            self._samples.clear()


# Sliding-window buffers feeding the AlertManager. Populated from the same
# record_* functions that update the Prometheus counters.
llm_outcomes = EventWindow()
turn_durations = EventWindow()
rag_outcomes = EventWindow()
telegram_outcomes = EventWindow()

# --- buckets -----------------------------------------------------------------
_STAGE_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.5, 10.0, 15.0, 30.0, 60.0)
_TURN_BUCKETS = (0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0, 15.0, 30.0, 60.0, 120.0)
_LLM_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0)
_SCORE_BUCKETS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
_HTTP_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)

# --- process -----------------------------------------------------------------
process_start_time_seconds = Gauge(
    "vanessa_process_start_time_seconds",
    "Unix time the process started (uptime source)",
    registry=registry,
)
process_start_time_seconds.set_to_current_time()

# --- pipeline ----------------------------------------------------------------
turns_total = Counter(
    "vanessa_turns_total",
    "Messages processed by the reply pipeline",
    ["action", "reason"],
    registry=registry,
)
turn_duration_seconds = Histogram(
    "vanessa_turn_duration_seconds",
    "End-to-end turn latency in seconds",
    ["action"],
    buckets=_TURN_BUCKETS,
    registry=registry,
)
stage_duration_seconds = Histogram(
    "vanessa_stage_duration_seconds",
    "Per-stage latency in seconds",
    ["stage"],
    buckets=_STAGE_BUCKETS,
    registry=registry,
)
background_queue_length = Gauge(
    "vanessa_background_queue_length",
    "Background executor queue length (0 = idle)",
    registry=registry,
)

# --- HTTP (API process) ------------------------------------------------------
http_requests_total = Counter(
    "vanessa_http_requests_total",
    "API HTTP requests served",
    ["method", "path", "status"],
    registry=registry,
)
http_request_duration_seconds = Histogram(
    "vanessa_http_request_duration_seconds",
    "API HTTP request latency in seconds",
    ["method", "path"],
    buckets=_HTTP_BUCKETS,
    registry=registry,
)

# --- HTTP client (bot -> API) -------------------------------------------------
http_client_requests_total = Counter(
    "vanessa_http_client_requests_total",
    "Outbound HTTP requests (bot -> API)",
    ["service", "status"],
    registry=registry,
)
http_client_duration_seconds = Histogram(
    "vanessa_http_client_duration_seconds",
    "Outbound HTTP request latency in seconds",
    ["service"],
    buckets=_HTTP_BUCKETS,
    registry=registry,
)

# --- LLM ---------------------------------------------------------------------
llm_requests_total = Counter(
    "vanessa_llm_requests_total",
    "LLM requests by outcome",
    ["provider", "model", "kind", "status"],
    registry=registry,
)
llm_tokens_total = Counter(
    "vanessa_llm_tokens_total",
    "LLM token usage by token type",
    ["provider", "model", "kind", "token_type"],
    registry=registry,
)
llm_errors_total = Counter(
    "vanessa_llm_errors_total",
    "LLM errors by error class",
    ["provider", "model", "kind", "error_type"],
    registry=registry,
)
llm_duration_seconds = Histogram(
    "vanessa_llm_duration_seconds",
    "LLM request latency in seconds",
    ["provider", "model", "kind"],
    buckets=_LLM_BUCKETS,
    registry=registry,
)

# --- RAG ---------------------------------------------------------------------
rag_search_total = Counter(
    "vanessa_rag_search_total",
    "RAG retrieval attempts",
    ["source"],
    registry=registry,
)
rag_hits_total = Counter(
    "vanessa_rag_hits_total",
    "RAG blocks returned",
    ["source"],
    registry=registry,
)
rag_score = Histogram(
    "vanessa_rag_score",
    "Top retrieval score per search (proxy for context relevance)",
    ["source"],
    buckets=_SCORE_BUCKETS,
    registry=registry,
)
rag_empty_total = Counter(
    "vanessa_rag_empty_total",
    "RAG searches that returned nothing",
    ["source"],
    registry=registry,
)

# --- Compose-prompt budget ---------------------------------------------------
prompt_budget_chars = Histogram(
    "vanessa_prompt_budget_chars",
    "Compose prompt section length in characters after the budget",
    ["section"],
    buckets=(500, 1000, 2000, 4000, 6000, 10000, 16000, 24000, 36000),
    registry=registry,
)
prompt_truncations_total = Counter(
    "vanessa_prompt_truncations_total",
    "Compose prompt sections truncated by the budget guard",
    ["section"],
    registry=registry,
)

# --- Telegram ----------------------------------------------------------------
telegram_requests_total = Counter(
    "vanessa_telegram_requests_total",
    "Telegram Bot API calls by outcome",
    ["operation", "status"],
    registry=registry,
)
telegram_errors_total = Counter(
    "vanessa_telegram_errors_total",
    "Telegram Bot API errors by class",
    ["operation", "error_type"],
    registry=registry,
)

# --- RAG Triad evaluation ------------------------------------------------------
rag_eval_score = Gauge(
    "vanessa_rag_eval_score",
    "RAG Triad evaluation score (0..1) by dimension",
    ["dimension"],
    registry=registry,
)
rag_eval_total = Counter(
    "vanessa_rag_eval_total",
    "RAG Triad evaluations completed",
    ["dimension"],
    registry=registry,
)


# --- helpers ------------------------------------------------------------------
def render_metrics() -> bytes:
    """Prometheus text exposition for GET /metrics."""
    return generate_latest(registry)


def queue_length() -> int:
    """Current background executor queue length (for the AlertManager)."""
    return int(background_queue_length._value.get())


def record_turn(action: str, reason: str) -> None:
    turns_total.labels(action=action, reason=reason).inc()


def record_stage(stage: str, seconds: float) -> None:
    stage_duration_seconds.labels(stage=stage).observe(seconds)


def record_turn_duration(action: str, seconds: float) -> None:
    turn_duration_seconds.labels(action=action).observe(seconds)
    turn_durations.add(seconds)


def record_background_queue(length: int) -> None:
    background_queue_length.set(length)


def record_http(method: str, path: str, status: int, seconds: float) -> None:
    http_requests_total.labels(method=method, path=path, status=str(status)).inc()
    http_request_duration_seconds.labels(method=method, path=path).observe(seconds)


def record_http_client(service: str, status: int | None, seconds: float) -> None:
    code = str(status) if status is not None else "error"
    http_client_requests_total.labels(service=service, status=code).inc()
    http_client_duration_seconds.labels(service=service).observe(seconds)


def record_llm_request(
    provider: str,
    model: str,
    kind: str,
    status: str,
) -> None:
    llm_requests_total.labels(provider=provider, model=model, kind=kind, status=status).inc()


def record_llm_usage(
    provider: str,
    model: str,
    kind: str,
    usage: Mapping[str, int] | None,
) -> None:
    if not usage:
        return
    prompt = int(usage.get("prompt_tokens") or usage.get("input") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output") or 0)
    total = int(usage.get("total_tokens") or (prompt + completion) or 0)
    llm_tokens_total.labels(provider=provider, model=model, kind=kind, token_type="prompt").inc(prompt)
    llm_tokens_total.labels(provider=provider, model=model, kind=kind, token_type="completion").inc(completion)
    llm_tokens_total.labels(provider=provider, model=model, kind=kind, token_type="total").inc(total)


def record_llm_duration(provider: str, model: str, kind: str, seconds: float) -> None:
    llm_duration_seconds.labels(provider=provider, model=model, kind=kind).observe(seconds)


def record_llm_error(
    provider: str,
    model: str,
    kind: str,
    error_type: str,
) -> None:
    llm_errors_total.labels(provider=provider, model=model, kind=kind, error_type=error_type).inc()


def record_llm_call(
    provider: str,
    model: str,
    kind: str,
    *,
    started: float,
    status: str,
    error_type: str | None = None,
    usage: Mapping[str, int] | None = None,
) -> None:
    """Record one LLM request: outcome, latency and tokens (if any)."""
    elapsed = time.perf_counter() - started
    record_llm_request(provider, model, kind, status)
    record_llm_duration(provider, model, kind, elapsed)
    llm_outcomes.add(status)
    if status == "error":
        record_llm_error(provider, model, kind, error_type or "unknown")
    else:
        record_llm_usage(provider, model, kind, usage)


def record_rag_search(
    source: str,
    hits: int,
    top_score: float | None,
) -> None:
    rag_search_total.labels(source=source).inc()
    rag_hits_total.labels(source=source).inc(hits)
    rag_outcomes.add((source, hits))
    if top_score is not None:
        rag_score.labels(source=source).observe(top_score)
    if hits == 0:
        rag_empty_total.labels(source=source).inc()


def record_prompt_budget(section: str, chars: int) -> None:
    """Record the final length of one compose-prompt section (after budget)."""
    prompt_budget_chars.labels(section=section).observe(chars)


def record_prompt_truncation(section: str) -> None:
    """Record that the budget guard trimmed/dropped a compose-prompt section."""
    prompt_truncations_total.labels(section=section).inc()


def record_telegram(operation: str, status: str) -> None:
    telegram_requests_total.labels(operation=operation, status=status).inc()
    telegram_outcomes.add((operation, status))


def record_telegram_error(operation: str, error_type: str) -> None:
    telegram_errors_total.labels(operation=operation, error_type=error_type).inc()
    telegram_outcomes.add((operation, "error"))


def record_rag_eval(dimension: str, score: float) -> None:
    rag_eval_score.labels(dimension=dimension).set(score)
    rag_eval_total.labels(dimension=dimension).inc()


def classify_llm_error(exc: Exception) -> str:
    """Map an exception to a coarse error class for the LLM error metric."""
    status = getattr(exc, "status_code", None)
    if status == 401 or status == 403:
        return "auth"
    if status == 402:
        return "insufficient_balance"
    if status == 429:
        return "rate_limit"
    if status is not None and 500 <= int(status) < 600:
        return "server_error"
    name = type(exc).__name__.lower()
    if "timeout" in name or "connect" in name or "transport" in name:
        return "network"
    return "unknown"


__all__ = [
    "CONTENT_TYPE_LATEST",
    "registry",
    "render_metrics",
    "record_turn",
    "record_stage",
    "record_turn_duration",
    "record_background_queue",
    "record_http",
    "record_http_client",
    "record_llm_call",
    "record_llm_request",
    "record_llm_usage",
    "record_llm_duration",
    "record_llm_error",
    "record_rag_search",
    "record_prompt_budget",
    "record_prompt_truncation",
    "record_telegram",
    "record_telegram_error",
    "record_rag_eval",
    "classify_llm_error",
]
