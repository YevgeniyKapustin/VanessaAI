from __future__ import annotations

from vanessa.infrastructure.observability.metrics.metrics_io import (
    _refresh_activity_gauges,
    knowledge_mutations_total,
    knowledge_search_hits_total,
    knowledge_vector_sync_duration_seconds,
    photo_request_missed_total,
    photo_send_total,
    reply_length_chars,
    telegram_errors_total,
    telegram_rate_limits_total,
    telegram_requests_total,
    web_search_duration_seconds,
    web_search_total,
)
from vanessa.infrastructure.observability.metrics.metrics_llm import (
    prompt_budget_chars,
    prompt_truncations_total,
    rag_empty_total,
    rag_eval_score,
    rag_eval_total,
    rag_hits_total,
    rag_score,
    rag_search_total,
)
from vanessa.infrastructure.observability.metrics.metrics_pipeline import (
    background_queue_length,
    broker_consumed_total,
    broker_dlq_total,
    broker_published_total,
    broker_rpc_duration_seconds,
    http_client_duration_seconds,
    http_client_requests_total,
    http_request_duration_seconds,
    http_requests_total,
    stage_duration_seconds,
    turn_duration_seconds,
    turns_total,
)
from vanessa.infrastructure.observability.metrics.metrics_window import (
    active_sessions_5m,
    active_users_1h,
    active_users_24h,
    rag_outcomes,
    telegram_limit_outcomes,
    telegram_outcomes,
    turn_durations,
)


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
