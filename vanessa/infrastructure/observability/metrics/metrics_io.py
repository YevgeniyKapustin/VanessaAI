from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

from vanessa.infrastructure.observability.metrics.metrics_pipeline import (
    registry,
)
from vanessa.infrastructure.observability.metrics.metrics_window import (
    active_sessions_5m,
    active_users_1h,
    active_users_24h,
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

# --- Knowledge vault --------------------------------------------------------
knowledge_mutations_total = Counter(
    "vanessa_knowledge_mutations_total",
    "Knowledge-node writes by type and action",
    ["type", "action"],
    registry=registry,
)
knowledge_database_pool_connections = Gauge(
    "vanessa_knowledge_database_pool_connections",
    "Postgres connection pool checked-out connections",
    registry=registry,
)


def _refresh_db_pool_gauge() -> None:
    try:
        # Lazy: importing session constructs the DB engine.
        from vanessa.infrastructure.db.session import engine  # noqa: PLC0415

        pool = engine.sync_engine.pool
        knowledge_database_pool_connections.set(int(pool.checkedout()))
    except Exception:  # noqa: BLE001
        return


def _refresh_activity_gauges() -> None:
    """Push the current unique-count windows into the activity gauges."""
    active_users.labels(scope="1h").set(len(set(active_users_1h.snapshot())))
    active_users.labels(scope="24h").set(len(set(active_users_24h.snapshot())))
    active_sessions.labels(scope="5m").set(len(set(active_sessions_5m.snapshot())))
    _refresh_db_pool_gauge()
