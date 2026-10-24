"""Token usage of one chat completion as a plain dict (metrics / traces)."""

from __future__ import annotations

from typing import Any


def _tokens(usage: Any, name: str) -> int:
    return int(getattr(usage, name, 0) or 0)


def anthropic_usage(response: Any) -> dict[str, int] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    prompt = _tokens(usage, "input_tokens")
    completion = _tokens(usage, "output_tokens")
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


def openai_usage(response: Any) -> dict[str, int] | None:
    """OpenAI-style usage plus the DeepSeek KV-cache split."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    return {
        "prompt_tokens": _tokens(usage, "prompt_tokens"),
        "completion_tokens": _tokens(usage, "completion_tokens"),
        "total_tokens": _tokens(usage, "total_tokens"),
        "cache_hit_tokens": _tokens(usage, "prompt_cache_hit_tokens"),
        "cache_miss_tokens": _tokens(usage, "prompt_cache_miss_tokens"),
    }
