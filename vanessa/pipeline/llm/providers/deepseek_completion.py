import logging
from typing import Any

from openai import APIStatusError

from vanessa.config.content import get_content
from vanessa.infrastructure.observability.metrics import record_llm_call
from vanessa.infrastructure.observability.tracing import get_tracer
from vanessa.pipeline.llm.completion_retry import run_completion_with_retries
from vanessa.pipeline.llm.format.answer_tag import extract_answer
from vanessa.pipeline.llm.format.profanity_substitution import ProfanitySubstitutor
from vanessa.pipeline.llm.format.reply_format import (
    capitalize_sentences,
    strip_leading_address,
    strip_trailing_periods,
)
from vanessa.pipeline.llm.providers.deepseek_usage import (
    _log_cache_usage,
    _usage_from_openai,
)

logger = logging.getLogger("vanessa.pipeline.llm.providers.deepseek")


class _DeepSeekCompletionMixin:
    def _should_retry(self, exc: Exception) -> bool:
        if isinstance(exc, APIStatusError):
            return exc.status_code in {429, 500, 502, 503, 529}
        return False

    def _substitute_profanity(self, text: str) -> str:
        substitutor = self._profanity
        if substitutor is None:
            substitutor = ProfanitySubstitutor.from_content(get_content())
        return substitutor.apply(text)

    def _reply_from_response(
        self,
        response: Any,
        *,
        model: str,
        started: float,
        sender_name: str | None,
        uses_vision: bool,
        image_count: int,
        gen: Any,
    ) -> str:
        text = response.choices[0].message.content or ""
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        if finish_reason == "length":
            logger.warning(
                "llm_truncated model=%s finish_reason=length "
                "content_chars=%s ends_with_marker=%s",
                model,
                len(text),
                text.rstrip().endswith("]"),
            )
        reasoning_content = getattr(
            response.choices[0].message, "reasoning_content", None
        ) or ""
        usage = _usage_from_openai(response)
        _log_cache_usage(model, usage)
        record_llm_call(
            provider="deepseek",
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
        cleaned = strip_leading_address(
            self._substitute_profanity(reply_text),
            sender_name,
        )
        reply = capitalize_sentences(strip_trailing_periods(cleaned))
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
                "images": image_count,
            },
            usage=usage or None,
        )
        return reply

    async def _run_completion(
        self,
        *,
        model: str,
        system: str,
        user_prompt: str,
        user_content: str | list[dict[str, Any]],
        sender_name: str | None,
        uses_vision: bool,
        image_count: int,
        generation_kwargs: dict[str, Any],
    ) -> str:
        async def complete(gen: Any, started: float) -> str:
            response = await self._openai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
                **generation_kwargs,
            )
            return self._reply_from_response(
                response,
                model=model,
                started=started,
                sender_name=sender_name,
                uses_vision=uses_vision,
                image_count=image_count,
                gen=gen,
            )

        return await run_completion_with_retries(
            get_tracer().generation(
                name="llm_generation",
                model=model,
                input={"system": system, "user": user_prompt},
                metadata={
                    "provider": "deepseek",
                    "kind": "generation",
                    "vision": uses_vision,
                    "images": image_count,
                },
            ),
            complete,
            provider="deepseek",
            model=model,
            max_retries=self._max_retries,
            should_retry=self._should_retry,
            sleep=self._retry_sleep,
            logger=logger,
        )
