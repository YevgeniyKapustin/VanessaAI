from __future__ import annotations

from vanessa.config.settings import settings

# USD per 1M tokens (input / output) for known models. Kept in sync with the
# provider price sheets; ``settings.llm_default_*_cost_per_1m`` is the fallback
# for any unlisted provider/model. Costs are estimates for monitoring spend —
# not a billing ledger.
_LLM_PRICING_PER_1M: dict[tuple[str, str], tuple[float, float]] = {
    ("deepseek", "deepseek-chat"): (0.27, 1.10),
    ("deepseek", "deepseek-reasoner"): (0.55, 2.19),
    # DeepSeek V4 prices vary by hour (off-peak/peak); the midpoint of the
    # published range is used as a single-point estimate for spend monitoring.
    # Flash (0731): input $0.14-0.22, output $0.28-0.66 -> (0.18, 0.47).
    ("deepseek", "deepseek-v4-flash"): (0.18, 0.47),
    # deepseek-flash (V4.1-Flash): the same price sheet as V4 Flash.
    ("deepseek", "deepseek-flash"): (0.18, 0.47),
    # Pro (0813): input $0.435-0.66, output $0.87-1.98 -> (0.5475, 1.425).
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
    # Flash (0731): cache-hit $0.0028-0.007 -> midpoint 0.0049.
    ("deepseek", "deepseek-v4-flash"): 0.0049,
    ("deepseek", "deepseek-flash"): 0.0049,
    # Pro (0813): cache-hit $0.0036-0.022 -> midpoint 0.0128.
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
