import asyncio
import logging
import time
from typing import Any

from openai import APIStatusError, AsyncOpenAI

from app.config.content import AppContent, MemeDefContent, get_content
from app.config.settings import settings
from app.core.messages import ContextBlock, ContextMessage, ImageAttachment, PhotoCandidate
from app.knowledge.schema import KnowledgeBlock
from app.llm.planner.generation_config import LLMGenerationParams
from app.llm.format.answer_tag import extract_answer
from app.llm.format.profanity_substitution import ProfanitySubstitutor
from app.llm.prompts.prompt_builder import PromptBuilder
from app.llm.format.reply_format import (
    capitalize_sentences,
    strip_leading_address,
    strip_trailing_periods,
)
from app.observability.metrics import classify_llm_error, record_llm_call
from app.observability.tracing import get_tracer

logger = logging.getLogger(__name__)


class DeepSeekLLMProvider:
    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        model: str | None = None,
        prompt_builder: PromptBuilder | None = None,
        profanity_substitutor: ProfanitySubstitutor | None = None,
        max_retries: int | None = None,
        generation: LLMGenerationParams | None = None,
        content: AppContent | None = None,
        pro_model: str | None = None,
        vision_model: str | None = None,
    ) -> None:
        self._content = content or get_content()
        self._client = client
        self._model = model or settings.deepseek_model
        # Upscaled model for super-complex synthesis / coding turns. Selected
        # per-call when generate(uses_pro_model=True) is set by the gate.
        self._pro_model = pro_model or settings.deepseek_pro_model
        # Multimodal model for turns that carry images (vision). Selected
        # per-call when generate(images=[...]) is non-empty.
        self._vision_model = vision_model or settings.deepseek_vision_model
        self._prompts = prompt_builder or PromptBuilder(self._content)
        self._profanity = profanity_substitutor
        self._max_retries = (
            max_retries
            if max_retries is not None
            else settings.llm_max_retries
        )
        self._generation = (
            generation
            or self._content.llm.generation.composer.to_params()
        )

    @property
    def _openai_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )
        return self._client

    def _should_retry(self, exc: Exception) -> bool:
        if isinstance(exc, APIStatusError):
            return exc.status_code in {429, 500, 502, 503, 529}
        return False

    def _substitute_profanity(self, text: str) -> str:
        substitutor = self._profanity
        if substitutor is None:
            from app.config.content import get_content

            substitutor = ProfanitySubstitutor.from_content(get_content())
        return substitutor.apply(text)

    async def generate(
        self,
        user_message: str,
        context_blocks: list[ContextBlock],
        session_messages: list[ContextMessage] | None = None,
        humor_quotes: list[str] | None = None,
        knowledge_blocks: list[KnowledgeBlock] | None = None,
        meme_blocks: list[MemeDefContent] | None = None,
        meme_menu: list[MemeDefContent] | None = None,
        metrics_block: str | None = None,
        attitude_note: str | None = None,
        *,
        sender_telegram_id: int | None = None,
        sender_name: str | None = None,
        system_prompt: str | None = None,
        tone: str | None = None,
        needs_clarification: bool = False,
        clarification_hint: str = "",
        detail: str = "normal",
        uses_pro_model: bool = False,
        reply_to_text: str | None = None,
        reply_to_sender_telegram_id: int | None = None,
        reply_to_sender_name: str | None = None,
        images: list[ImageAttachment] | None = None,
        photo_candidates: list[PhotoCandidate] | None = None,
    ) -> str:
        # Route complex turns (coding / deep synthesis, flagged by the gate)
        # to the upscaled model; a turn with images goes to the vision model;
        # everything else stays on the fast default.
        uses_vision = bool(images)
        if uses_vision:
            model = self._vision_model
        else:
            model = self._pro_model if uses_pro_model else self._model
        system = system_prompt or self._prompts.system_prompt
        user_prompt = self._prompts.build_user_prompt(
            user_message,
            context_blocks,
            session_messages=session_messages,
            humor_quotes=humor_quotes,
            knowledge_blocks=knowledge_blocks,
            meme_blocks=meme_blocks,
            meme_menu=meme_menu,
            metrics_block=metrics_block,
            attitude_note=attitude_note,
            sender_telegram_id=sender_telegram_id,
            sender_name=sender_name,
            tone=tone,
            needs_clarification=needs_clarification,
            clarification_hint=clarification_hint,
            detail=detail,
            reply_to_text=reply_to_text,
            reply_to_sender_telegram_id=reply_to_sender_telegram_id,
            reply_to_sender_name=reply_to_sender_name,
            has_image=uses_vision,
            photo_candidates=photo_candidates,
        )
        message_count = sum(len(block.messages) for block in context_blocks)
        knowledge_chars = sum(
            len(block.content or "") for block in (knowledge_blocks or [])
        )
        session_chars = sum(
            len(message.content or "") for message in (session_messages or [])
        )
        # Effective sampling params; a "detailed" reply gets more room so a
        # fuller answer is not truncated (headroom for the reasoning prefix too).
        generation_kwargs = self._generation.to_llm_kwargs()
        if (
            detail == "detailed"
            and self._content.llm.detailed_max_tokens > 0
        ):
            generation_kwargs["max_tokens"] = self._content.llm.detailed_max_tokens
        logger.info(
            "llm_prompt_prepared model=%s uses_pro_model=%s detail=%s "
            "context_blocks=%s context_messages=%s humor_quotes=%s meme_blocks=%s "
            "meme_menu=%s system_chars=%s user_chars=%s knowledge_blocks=%s "
            "knowledge_chars=%s session_chars=%s temperature=%s top_p=%s "
            "max_tokens=%s vision_images=%s",
            model,
            uses_pro_model,
            detail,
            len(context_blocks),
            message_count,
            len(humor_quotes or []),
            len(meme_blocks or []),
            len(meme_menu or []),
            len(system),
            len(user_prompt),
            len(knowledge_blocks or []),
            knowledge_chars,
            session_chars,
            self._generation.temperature,
            self._generation.top_p,
            generation_kwargs.get("max_tokens"),
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

        # OpenAI multimodal content: text + image_url blocks when the turn has
        # images, otherwise the plain string prompt (backwards compatible).
        if uses_vision:
            user_content: str | list[dict[str, Any]] = [
                {"type": "text", "text": user_prompt}
            ]
            for image in images or []:
                user_content.append(
                    {"type": "image_url", "image_url": {"url": image.data_url}}
                )
        else:
            user_content = user_prompt

        provider = "deepseek"
        tracer = get_tracer()
        last_error: Exception | None = None
        async with tracer.generation(
            name="llm_generation",
            model=model,
            input={"system": system, "user": user_prompt},
            metadata={
                "provider": provider,
                "kind": "generation",
                "vision": uses_vision,
                "images": len(images or []),
            },
        ) as gen:
            for attempt in range(self._max_retries + 1):
                started = time.perf_counter()
                try:
                    response = await self._openai_client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user_content},
                        ],
                        **generation_kwargs,
                    )
                    text = response.choices[0].message.content or ""
                    # DeepSeek reasoning models put the chain of thought here; it
                    # is separate from ``content`` and would otherwise be invisible.
                    reasoning_content = getattr(
                        response.choices[0].message, "reasoning_content", None
                    ) or ""
                    usage = _usage_from_openai(response)
                    _log_cache_usage(model, usage)
                    record_llm_call(
                        provider=provider,
                        model=model,
                        kind="generation",
                        started=started,
                        status="success",
                        usage=usage,
                        output=text,
                    )
                    reply_text, reasoning = extract_answer(text)
                    if reasoning:
                        logger.info(
                            "llm_reasoning model=%s reasoning=%r",
                            model,
                            reasoning,
                        )
                    # The reasoning never leaves this method: only the text after
                    # the [answer] tag is post-processed and returned.
                    cleaned = strip_leading_address(
                        self._substitute_profanity(reply_text),
                        sender_name,
                    )
                    reply = capitalize_sentences(strip_trailing_periods(cleaned))
                    # Surface the FULL raw model output (reasoning + the [answer]
                    # tag + the [next] block markers) so block-splitting and the
                    # chain of thought are debuggable in Langfuse / logs; the
                    # processed reply stays in metadata.
                    raw_output = text
                    if reasoning_content:
                        raw_output = f"[reasoning_content]\n{reasoning_content}\n\n{text}"
                    logger.debug("llm_raw_output model=%s output=%r", model, raw_output)
                    gen.update(
                        output=raw_output,
                        metadata={
                            "reasoning": reasoning,
                            "reasoning_content": reasoning_content,
                            "reply": reply,
                            "vision": uses_vision,
                            "images": len(images or []),
                        },
                        usage=usage or None,
                    )
                    return reply
                except Exception as exc:
                    last_error = exc
                    record_llm_call(
                        provider=provider,
                        model=model,
                        kind="generation",
                        started=started,
                        status="error",
                        error_type=classify_llm_error(exc),
                    )
                    if attempt >= self._max_retries or not self._should_retry(exc):
                        raise
                    delay = 1.0 * (attempt + 1)
                    logger.warning(
                        "LLM request failed (attempt %s/%s), retry in %.1fs: %s",
                        attempt + 1,
                        self._max_retries + 1,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
            assert last_error is not None
            raise last_error


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
