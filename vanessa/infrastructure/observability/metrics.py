from __future__ import annotations

import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from vanessa.config.settings import settings

logger = logging.getLogger(__name__)

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

# --- Broker (Redis Streams transport) ----------------------------------------
broker_published_total = Counter(
    "vanessa_broker_published_total",
    "Messages published to broker streams",
    ["stream", "kind"],
    registry=registry,
)
broker_consumed_total = Counter(
    "vanessa_broker_consumed_total",
    "Messages consumed from broker streams",
    ["stream", "kind"],
    registry=registry,
)
broker_dlq_total = Counter(
    "vanessa_broker_dlq_total",
    "Messages moved to a dead-letter stream",
    ["stream"],
    registry=registry,
)
broker_rpc_duration_seconds = Histogram(
    "vanessa_broker_rpc_duration_seconds",
    "Broker RPC round-trip latency in seconds",
    ["kind"],
    buckets=_TURN_BUCKETS,
    registry=registry,
)
# Queue health gauges refreshed by BrokerMetricsCollector.
broker_stream_length = Gauge(
    "vanessa_broker_stream_length",
    "Number of entries in a broker stream",
    ["stream"],
    registry=registry,
)
broker_consumer_lag = Gauge(
    "vanessa_broker_consumer_lag",
    "Pending (unacked) entries for a consumer group",
    ["stream", "group"],
    registry=registry,
)
broker_dlq_depth = Gauge(
    "vanessa_broker_dlq_depth",
    "Number of entries in a dead-letter stream",
    ["stream"],
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
telegram_rate_limits_total = Counter(
    "vanessa_telegram_rate_limits_total",
    "Telegram 429/flood and blocked-by-user errors",
    ["operation", "error_type"],
    registry=registry,
)

# --- LLM cost & output quality ---------------------------------------------
llm_cost_total = Counter(
    "vanessa_llm_cost_total",
    "Estimated LLM API cost in USD by token type",
    ["provider", "model", "kind", "token_type"],
    registry=registry,
)
llm_empty_total = Counter(
    "vanessa_llm_empty_total",
    "LLM completions that returned empty or whitespace text",
    ["provider", "model", "kind"],
    registry=registry,
)
llm_cache_hit_tokens_total = Counter(
    "vanessa_llm_cache_hit_tokens_total",
    "LLM prompt tokens served from the provider KV-cache (cache hit)",
    ["provider", "model", "kind"],
    registry=registry,
)
llm_cache_miss_tokens_total = Counter(
    "vanessa_llm_cache_miss_tokens_total",
    "LLM prompt tokens re-encoded because of a KV-cache miss",
    ["provider", "model", "kind"],
    registry=registry,
)

# --- Stickers ---------------------------------------------------------------
sticker_unknown_tags_total = Counter(
    "vanessa_sticker_unknown_tags_total",
    "Sticker tags the model emitted that are not in the pack (soft fallback outcome)",
    ["action"],  # mapped | dropped
    registry=registry,
)
sticker_tagged_total = Counter(
    "vanessa_sticker_tagged_total",
    "Sticker tags accepted from the LLM reply (after alias mapping)",
    ["tag"],
    registry=registry,
)

# --- Photo sending ----------------------------------------------------------
photo_send_total = Counter(
    "vanessa_photo_send_total",
    "Photo delivery outcomes: requested / resolved / delivered / failed / missed",
    ["status"],
    registry=registry,
)
photo_request_missed_total = Counter(
    "vanessa_photo_request_missed_total",
    "User explicitly asked for a photo but no photo_file_id was resolved "
    "(the 'сказала что отправила, но фото не пришло' bug)",
    ["reason"],  # no_marker | index_out_of_range | album_empty
    registry=registry,
)

# --- Web search (the "googling" skill) ----------------------------------------
web_search_total = Counter(
    "vanessa_web_search_total",
    "Live web-search outcomes per turn: attempted / found / empty / error",
    ["status"],
    registry=registry,
)
web_search_duration_seconds = Histogram(
    "vanessa_web_search_duration_seconds",
    "Live web-search API latency (seconds)",
    registry=registry,
)

# --- User activity / engagement ---------------------------------------------
active_users = Gauge(
    "vanessa_active_users",
    "Unique active senders over a rolling window",
    ["scope"],  # 1h | 24h
    registry=registry,
)
active_sessions = Gauge(
    "vanessa_active_sessions",
    "Unique active Telegram chats over a rolling window (concurrent dialogs)",
    ["scope"],  # 5m
    registry=registry,
)

# --- Reply quality ----------------------------------------------------------
reply_length_chars = Histogram(
    "vanessa_reply_length_chars",
    "Final bot reply length in characters",
    ["action"],
    buckets=(50, 100, 200, 400, 700, 1000, 1500, 2500, 4000, 6000),
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

# --- Knowledge vault --------------------------------------------------------
knowledge_mutations_total = Counter(
    "vanessa_knowledge_mutations_total",
    "Knowledge-node writes by type and action",
    ["type", "action"],
    registry=registry,
)
knowledge_vector_sync_duration_seconds = Histogram(
    "vanessa_knowledge_vector_sync_duration_seconds",
    "Time to embed a knowledge node and upsert it into Qdrant",
    buckets=_STAGE_BUCKETS,
    registry=registry,
)
knowledge_search_hits_total = Counter(
    "vanessa_knowledge_search_hits_total",
    "Knowledge search hits by backend",
    ["source"],
    registry=registry,
)
knowledge_database_pool_connections = Gauge(
    "vanessa_knowledge_database_pool_connections",
    "Postgres connection pool checked-out connections",
    registry=registry,
)


# --- helpers ------------------------------------------------------------------

# USD per 1M tokens (input / output) for known models. Kept in sync with the
# provider price sheets; ``settings.llm_default_*_cost_per_1m`` is the fallback
# for any unlisted provider/model. Costs are estimates for monitoring spend —
# not a billing ledger.
_LLM_PRICING_PER_1M: dict[tuple[str, str], tuple[float, float]] = {
    ("deepseek", "deepseek-chat"): (0.27, 1.10),
    ("deepseek", "deepseek-reasoner"): (0.55, 2.19),
    # DeepSeek V4 prices vary by hour (off-peak/peak); the midpoint of the
    # published range is used as a single-point estimate for spend monitoring.
    # Flash (0731): input $0.14–0.22, output $0.28–0.66 -> (0.18, 0.47).
    ("deepseek", "deepseek-v4-flash"): (0.18, 0.47),
    # Pro (0813): input $0.435–0.66, output $0.87–1.98 -> (0.5475, 1.425).
    ("deepseek", "deepseek-v4-pro"): (0.5475, 1.425),
    ("claude", "claude-sonnet-4-6"): (3.00, 15.00),
    ("claude", "claude-sonnet-4-5"): (3.00, 15.00),
    ("claude", "claude-haiku-4-5"): (1.00, 5.00),
}

# USD per 1M cache-hit input tokens (DeepSeek KV-cache billing). Tokens served
# from the cache cost a fraction of a re-encode, so the cost estimate splits
# input into cache-hit (this price) and cache-miss (the prompt price above).
# V4 values are the midpoint of the published hourly ranges;
# ``settings.llm_default_cache_hit_prompt_cost_per_1m`` is the fallback.
_LLM_CACHE_HIT_PROMPT_PRICE_PER_1M: dict[tuple[str, str], float] = {
    ("deepseek", "deepseek-chat"): 0.07,
    # Flash (0731): cache-hit $0.0028–0.007 -> midpoint 0.0049.
    ("deepseek", "deepseek-v4-flash"): 0.0049,
    # Pro (0813): cache-hit $0.0036–0.022 -> midpoint 0.0128.
    ("deepseek", "deepseek-v4-pro"): 0.0128,
}


def llm_price_per_1m(provider: str, model: str) -> tuple[float, float]:
    """USD per 1M tokens ``(prompt, completion)`` for a provider+model."""
    return _LLM_PRICING_PER_1M.get(
        (provider, model),
        (
            settings.llm_default_prompt_cost_per_1m,
            settings.llm_default_completion_cost_per_1m,
        ),
    )


def llm_cache_hit_prompt_price_per_1m(provider: str, model: str) -> float:
    """USD per 1M cache-hit input tokens for a provider+model."""
    return _LLM_CACHE_HIT_PROMPT_PRICE_PER_1M.get(
        (provider, model),
        settings.llm_default_cache_hit_prompt_cost_per_1m,
    )


def _prompt_input_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    cache_hit_tokens: int,
) -> float:
    """USD cost of the input tokens, splitting cache-hit vs cache-miss pricing."""
    prompt_usd, _ = llm_price_per_1m(provider, model)
    cache_hit_usd = llm_cache_hit_prompt_price_per_1m(provider, model)
    hit = min(max(cache_hit_tokens, 0), prompt_tokens)
    miss = max(prompt_tokens - hit, 0)
    return miss / 1_000_000 * prompt_usd + hit / 1_000_000 * cache_hit_usd


def estimate_llm_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cache_hit_tokens: int = 0,
) -> float:
    """Estimate the USD cost of one LLM call from its token usage.

    ``cache_hit_tokens`` (from ``prompt_cache_hit_tokens``) are billed at the
    discounted KV-cache input price, so a well-cached RAG prompt is far cheaper
    than its raw token count suggests.
    """
    _, completion_usd = llm_price_per_1m(provider, model)
    return (
        _prompt_input_cost(provider, model, prompt_tokens, cache_hit_tokens)
        + completion_tokens / 1_000_000 * completion_usd
    )


def _refresh_activity_gauges() -> None:
    """Push the current unique-count windows into the activity gauges."""
    active_users.labels(scope="1h").set(len(set(active_users_1h.snapshot())))
    active_users.labels(scope="24h").set(len(set(active_users_24h.snapshot())))
    active_sessions.labels(scope="5m").set(len(set(active_sessions_5m.snapshot())))
    _refresh_db_pool_gauge()


def _refresh_db_pool_gauge() -> None:
    try:
        from vanessa.infrastructure.db.session import engine

        pool = engine.sync_engine.pool
        knowledge_database_pool_connections.set(int(pool.checkedout()))
    except Exception:
        return


def render_metrics() -> bytes:
    """Prometheus text exposition for GET /metrics (activity gauges refreshed)."""
    _refresh_activity_gauges()
    return generate_latest(registry)


def metrics_token_allowed(headers: Mapping[str, str]) -> bool:
    """True when /metrics may be served for these request headers."""
    if not settings.metrics_require_token:
        return True
    expected = settings.api_internal_token.strip()
    if not expected:
        return True
    header = str(headers.get("X-Internal-Token") or "").strip()
    auth = str(headers.get("Authorization") or "")
    bearer = ""
    if auth.lower().startswith("bearer "):
        bearer = auth[7:].strip()
    return header == expected or bearer == expected


class _ProcessHttpHandler(BaseHTTPRequestHandler):
    """Serve /health for probes and /metrics for Prometheus."""

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/health", "/health/live", "/health/ready"):
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/metrics":
            if not metrics_token_allowed(self.headers):
                body = b"unauthorized\n"
                self.send_response(401)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if settings.metrics_enabled:
                body = render_metrics()
            else:
                body = b"# metrics disabled\n"
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = b"not found\n"
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_metrics_http_server(
    port: int, addr: str = "0.0.0.0"
) -> ThreadingHTTPServer:
    """Always serve /health. /metrics is empty when metrics are off."""
    server = ThreadingHTTPServer((addr, int(port)), _ProcessHttpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


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


def record_user_activity(user_id: int, chat_id: int) -> None:
    """Track an active sender and chat; refreshes the activity gauges."""
    active_users_1h.add(user_id)
    active_users_24h.add(user_id)
    active_sessions_5m.add(chat_id)
    _refresh_activity_gauges()


def record_reply_length(action: str, chars: int) -> None:
    """Record the final reply length in characters (quality signal)."""
    reply_length_chars.labels(action=action).observe(chars)


def record_http(method: str, path: str, status: int, seconds: float) -> None:
    http_requests_total.labels(method=method, path=path, status=str(status)).inc()
    http_request_duration_seconds.labels(method=method, path=path).observe(seconds)


def record_http_client(service: str, status: int | None, seconds: float) -> None:
    code = str(status) if status is not None else "error"
    http_client_requests_total.labels(service=service, status=code).inc()
    http_client_duration_seconds.labels(service=service).observe(seconds)


def record_broker_publish(stream: str, kind: str) -> None:
    broker_published_total.labels(stream=stream, kind=kind).inc()


def record_broker_consume(stream: str, kind: str) -> None:
    broker_consumed_total.labels(stream=stream, kind=kind).inc()


def record_broker_dlq(stream: str) -> None:
    broker_dlq_total.labels(stream=stream).inc()


def record_broker_rpc(kind: str, seconds: float) -> None:
    broker_rpc_duration_seconds.labels(kind=kind).observe(seconds)


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
    cache_hit = int(usage.get("cache_hit_tokens") or 0)
    cache_miss = int(usage.get("cache_miss_tokens") or 0)
    llm_tokens_total.labels(provider=provider, model=model, kind=kind, token_type="prompt").inc(prompt)
    llm_tokens_total.labels(provider=provider, model=model, kind=kind, token_type="completion").inc(completion)
    llm_tokens_total.labels(provider=provider, model=model, kind=kind, token_type="total").inc(total)
    if cache_hit or cache_miss:
        llm_cache_hit_tokens_total.labels(provider=provider, model=model, kind=kind).inc(cache_hit)
        llm_cache_miss_tokens_total.labels(provider=provider, model=model, kind=kind).inc(cache_miss)
    prompt_cost = _prompt_input_cost(provider, model, prompt, cache_hit)
    _, completion_usd = llm_price_per_1m(provider, model)
    completion_cost = completion / 1_000_000 * completion_usd
    cost = prompt_cost + completion_cost
    if cost <= 0:
        return
    llm_cost_total.labels(provider=provider, model=model, kind=kind, token_type="prompt").inc(prompt_cost)
    llm_cost_total.labels(provider=provider, model=model, kind=kind, token_type="completion").inc(completion_cost)
    llm_cost_total.labels(provider=provider, model=model, kind=kind, token_type="total").inc(cost)
    llm_cost_outcomes.add(cost)


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
    output: str | None = None,
) -> None:
    """Record one LLM request: outcome, latency, tokens, cost and empty output."""
    elapsed = time.perf_counter() - started
    record_llm_request(provider, model, kind, status)
    record_llm_duration(provider, model, kind, elapsed)
    llm_outcomes.add(status)
    if status == "error":
        record_llm_error(provider, model, kind, error_type or "unknown")
    else:
        record_llm_usage(provider, model, kind, usage)
        if output is not None and not output.strip():
            llm_empty_total.labels(provider=provider, model=model, kind=kind).inc()
            llm_empty_outcomes.add(1)
            logger.warning(
                "llm_empty_output provider=%s model=%s kind=%s usage=%s output_repr=%r",
                provider,
                model,
                kind,
                dict(usage) if usage else None,
                (output or "")[:80],
            )


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
    if error_type in {"flood", "blocked"}:
        telegram_rate_limits_total.labels(operation=operation, error_type=error_type).inc()
        telegram_limit_outcomes.add((operation, error_type))


def record_photo_send(status: str) -> None:
    """Record one photo-delivery outcome (requested/resolved/delivered/failed)."""
    photo_send_total.labels(status=status).inc()


def record_photo_request_missed(reason: str) -> None:
    """Record a photo request that resolved to no actual delivery.

    ``reason`` is one of ``no_marker`` / ``index_out_of_range`` / ``album_empty``
    — the exact "сказала что отправила, но фото не пришло" failure.
    """
    photo_request_missed_total.labels(reason=reason).inc()
    record_photo_send("missed")


def record_web_search(status: str, ms: float) -> None:
    """Record one live web-search outcome and its latency.

    ``status`` is ``found`` / ``empty`` / ``error`` (the Retrieve stage fails
    open on errors, so an ``error`` here never blocks the turn).
    """
    web_search_total.labels(status=status).inc()
    web_search_duration_seconds.observe(ms / 1000.0)


def record_rag_eval(dimension: str, score: float) -> None:
    rag_eval_score.labels(dimension=dimension).set(score)
    rag_eval_total.labels(dimension=dimension).inc()


def record_knowledge_mutation(node_type: str, action: str) -> None:
    knowledge_mutations_total.labels(type=node_type, action=action).inc()


def record_knowledge_vector_sync(seconds: float) -> None:
    knowledge_vector_sync_duration_seconds.observe(seconds)


def record_knowledge_search(source: str, hits: int) -> None:
    knowledge_search_hits_total.labels(source=source).inc(hits)


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
    "start_metrics_http_server",
    "record_turn",
    "record_stage",
    "record_turn_duration",
    "record_background_queue",
    "record_user_activity",
    "record_reply_length",
    "record_http",
    "record_http_client",
    "record_llm_call",
    "record_llm_request",
    "record_llm_usage",
    "record_llm_duration",
    "record_llm_error",
    "estimate_llm_cost",
    "llm_price_per_1m",
    "llm_cache_hit_prompt_price_per_1m",
    "record_rag_search",
    "record_prompt_budget",
    "record_prompt_truncation",
    "record_telegram",
    "record_telegram_error",
    "record_photo_send",
    "record_photo_request_missed",
    "record_rag_eval",
    "record_knowledge_mutation",
    "record_knowledge_vector_sync",
    "record_knowledge_search",
    "classify_llm_error",
]
