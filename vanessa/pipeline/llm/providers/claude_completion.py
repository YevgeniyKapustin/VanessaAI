import logging
from typing import Any

from anthropic import APIStatusError

from vanessa.config.content import get_content
from vanessa.infrastructure.observability.metrics import record_llm_call
from vanessa.infrastructure.observability.tracing import get_tracer
from vanessa.pipeline.llm.completion_retry import run_completion_with_retries
from vanessa.pipeline.llm.format.profanity_substitution import ProfanitySubstitutor
from vanessa.pipeline.llm.format.reply_format import (
    capitalize_sentences,
    strip_leading_address,
    strip_trailing_periods,
)
from vanessa.pipeline.llm.tagged_reply import request_tagged, split_reply

logger = logging.getLogger("vanessa.pipeline.llm.providers.claude")


def _first_text(response: Any) -> str:
    return response.content[0].text


def _usage_from_anthropic(response: Any) -> dict[str, int] | None:
    """Normalize an Anthropic Usage into a dict, or None if absent."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    prompt = int(getattr(usage, "input_tokens", 0) or 0)
    completion = int(getattr(usage, "output_tokens", 0) or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


class _ClaudeCompletionMixin:
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
        started: float,
        sender_name: str | None,
        gen: Any,
    ) -> str:
        text = _first_text(response)
        usage = _usage_from_anthropic(response)
        record_llm_call(
            provider="claude",
            model=self._model,
            kind="generation",
            started=started,
            status="success",
            usage=usage,
            output=text,
        )
        reply_text, reasoning = split_reply(text, self._model)
        if reasoning:
            logger.info(
                "llm_reasoning model=%s reasoning=%r",
                self._model,
                reasoning,
            )
        # The reasoning never leaves this method: only the text after
        # the [answer] tag is post-processed and returned.
        cleaned = strip_leading_address(
            self._substitute_profanity(reply_text),
            sender_name,
        )
        reply = capitalize_sentences(strip_trailing_periods(cleaned))
        # Surface the FULL raw model output (the [answer] tag + the
        # [next] block markers) so block-splitting is debuggable in
        # Langfuse / logs; the processed reply stays in metadata.
        logger.debug(
            "llm_raw_output model=%s output=%r",
            self._model,
            text,
        )
        gen.update(
            output=text,
            metadata={"reasoning": reasoning, "reply": reply},
            usage=usage or None,
        )
        return reply

    async def _run_completion(
        self,
        *,
        system: str,
        user_prompt: str,
        sender_name: str | None,
        generation_kwargs: dict[str, Any],
    ) -> str:
        async def complete(gen: Any, started: float) -> str:
            response = await request_tagged(
                lambda: self._client.messages.create(
                    model=self._model,
                    system=system,
                    messages=[{"role": "user", "content": user_prompt}],
                    **generation_kwargs,
                ),
                _first_text,
                model=self._model,
            )
            return self._reply_from_response(
                response,
                started=started,
                sender_name=sender_name,
                gen=gen,
            )

        return await run_completion_with_retries(
            get_tracer().generation(
                name="llm_generation",
                model=self._model,
                input={"system": system, "user": user_prompt},
                metadata={"provider": "claude", "kind": "generation"},
            ),
            complete,
            provider="claude",
            model=self._model,
            max_retries=self._max_retries,
            should_retry=self._should_retry,
            sleep=self._retry_sleep,
            logger=logger,
        )
