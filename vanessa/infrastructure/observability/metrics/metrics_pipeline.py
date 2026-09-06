from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

# Dedicated registry so the app and its tests never collide with the global
# default registry (which other libraries may populate).
registry = CollectorRegistry(auto_describe=False)

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
