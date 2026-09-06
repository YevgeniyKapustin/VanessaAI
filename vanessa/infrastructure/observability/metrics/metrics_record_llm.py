from __future__ import annotations

import logging
import time
from collections.abc import Mapping

from vanessa.infrastructure.observability.metrics.metrics_llm import (
    llm_cache_hit_tokens_total,
    llm_cache_miss_tokens_total,
    llm_cost_total,
    llm_duration_seconds,
    llm_empty_total,
    llm_errors_total,
    llm_requests_total,
    llm_tokens_total,
)
from vanessa.infrastructure.observability.metrics.metrics_pricing import (
    _prompt_input_cost,
    llm_price_per_1m,
)
from vanessa.infrastructure.observability.metrics.metrics_window import (
    llm_cost_outcomes,
    llm_empty_outcomes,
    llm_outcomes,
)

logger = logging.getLogger("vanessa.infrastructure.observability.metrics")

_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_PAYMENT_REQUIRED = 402
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_SERVER_ERROR_START = 500
_HTTP_SERVER_ERROR_END = 600


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
        return
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


def _auth_balance_class(status: object) -> str | None:
    if status in {_HTTP_UNAUTHORIZED, _HTTP_FORBIDDEN}:
        return "auth"
    if status == _HTTP_PAYMENT_REQUIRED:
        return "insufficient_balance"
    return None


def _rate_server_class(status: object) -> str | None:
    if status == _HTTP_TOO_MANY_REQUESTS:
        return "rate_limit"
    if status is None:
        return None
    if _HTTP_SERVER_ERROR_START <= int(status) < _HTTP_SERVER_ERROR_END:
        return "server_error"
    return None


def _network_or_unknown(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    if "timeout" in name or "connect" in name or "transport" in name:
        return "network"
    return "unknown"


def classify_llm_error(exc: Exception) -> str:
    """Map an exception to a coarse error class for the LLM error metric."""
    status = getattr(exc, "status_code", None)
    classified = _auth_balance_class(status) or _rate_server_class(status)
    if classified is not None:
        return classified
    return _network_or_unknown(exc)
