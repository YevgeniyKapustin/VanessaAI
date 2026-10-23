from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

from vanessa.infrastructure.observability.metrics.metrics_pipeline import (
    _LLM_BUCKETS,
    registry,
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
