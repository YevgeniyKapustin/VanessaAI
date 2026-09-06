import logging
from typing import Any

from vanessa.core.generate_request import GenerateRequest, prompt_log_counts
from vanessa.core.messages import ImageAttachment

logger = logging.getLogger("vanessa.pipeline.llm.providers.deepseek")


def _usage_from_openai(response: Any) -> dict[str, int] | None:
    """Normalize an OpenAI CompletionUsage into a dict, or None if absent.

    Includes the DeepSeek KV-cache split (``prompt_cache_hit_tokens`` /
    ``prompt_cache_miss_tokens``) so cost estimates can apply the discounted
    cache-hit input price and caching effectiveness can be monitored.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    return {
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        "cache_hit_tokens": int(getattr(usage, "prompt_cache_hit_tokens", 0) or 0),
        "cache_miss_tokens": int(getattr(usage, "prompt_cache_miss_tokens", 0) or 0),
    }


def _log_cache_usage(model: str, usage: dict[str, int] | None) -> None:
    """Log the KV-cache split (prompt_cache_hit_tokens) for one call."""
    if not usage:
        return
    hit = int(usage.get("cache_hit_tokens") or 0)
    miss = int(usage.get("cache_miss_tokens") or 0)
    if hit + miss <= 0:
        return
    logger.info(
        "llm_cache model=%s prompt_tokens=%s cache_hit=%s cache_miss=%s "
        "cache_hit_ratio=%.3f",
        model,
        int(usage.get("prompt_tokens") or 0),
        hit,
        miss,
        hit / (hit + miss),
    )


def log_deepseek_prompt(
    request: GenerateRequest,
    *,
    model: str,
    system: str,
    user_prompt: str,
    temperature: float,
    top_p: float,
    max_tokens: object,
) -> None:
    message_count, knowledge_chars, session_chars = prompt_log_counts(request)
    images: list[ImageAttachment] | None = request.images
    uses_vision = bool(images)
    logger.info(
        "llm_prompt_prepared model=%s uses_pro_model=%s detail=%s "
        "context_blocks=%s context_messages=%s humor_quotes=%s meme_blocks=%s "
        "meme_menu=%s system_chars=%s user_chars=%s knowledge_blocks=%s "
        "web_blocks=%s knowledge_chars=%s session_chars=%s temperature=%s "
        "top_p=%s max_tokens=%s vision_images=%s",
        model,
        request.uses_pro_model,
        request.detail,
        len(request.context_blocks),
        message_count,
        len(request.humor_quotes or []),
        len(request.meme_blocks or []),
        len(request.meme_menu or []),
        len(system),
        len(user_prompt),
        len(request.knowledge_blocks or []),
        len(request.web_blocks or []),
        knowledge_chars,
        session_chars,
        temperature,
        top_p,
        max_tokens,
        len(images or []),
    )
    logger.info("llm_system_prompt:\n%s", system)
    logger.info("llm_user_prompt:\n%s", user_prompt)
    if uses_vision:
        logger.info(
            "llm_vision model=%s images=%s mime_types=%s",
            model,
            len(images or []),
            [image.mime_type for image in (images or [])],
        )
