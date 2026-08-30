import logging
import time
from typing import Any

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from vanessa.config.settings import settings
from vanessa.core.protocols import LLMChatCompleter
from vanessa.infrastructure.observability.metrics import (
    classify_llm_error,
    record_llm_call,
)
from vanessa.infrastructure.observability.tracing import get_tracer

logger = logging.getLogger(__name__)


class _InstrumentedCompleterMixin:
    """Shared metrics/tracing around a single chat completion."""

    @property
    def provider(self) -> str:
        raise NotImplementedError

    async def _run_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        kind: str,
        call,
    ) -> str:
        started = time.perf_counter()
        tracer = get_tracer()
        async with tracer.generation(
            name=f"llm_{kind}",
            model=model,
            input=messages,
            metadata={"provider": self.provider, "kind": kind},
        ) as gen:
            try:
                text, usage, reasoning = await call()
            except Exception as exc:
                record_llm_call(
                    provider=self.provider,
                    model=model,
                    kind=kind,
                    started=started,
                    status="error",
                    error_type=classify_llm_error(exc),
                )
                raise
            if reasoning:
                gen.update(
                    output=f"[reasoning_content]\n{reasoning}\n\n{text}",
                    metadata={"reasoning_content": reasoning},
                    usage=usage or None,
                )
                logger.debug(
                    "llm_reasoning_content kind=%s model=%s chars=%s head=%r",
                    kind,
                    model,
                    len(reasoning),
                    reasoning[:120],
                )
            else:
                gen.update(output=text, usage=usage or None)
        record_llm_call(
            provider=self.provider,
            model=model,
            kind=kind,
            started=started,
            status="success",
            usage=usage,
            output=text,
        )
        return text


class ClaudeChatCompleter(_InstrumentedCompleterMixin):
    def __init__(self, client: AsyncAnthropic | None = None) -> None:
        self._client = client or AsyncAnthropic(api_key=settings.anthropic_api_key)

    @property
    def provider(self) -> str:
        return "claude"

    async def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        kind: str = "completion",
        **kwargs: Any,
    ) -> str:
        async def call() -> tuple[str, dict[str, int] | None, str]:
            kwargs.pop("reasoning_effort", None)
            response = await self._client.messages.create(
                model=model,
                messages=messages,
                **kwargs,
            )
            usage = getattr(response, "usage", None)
            prompt = int(getattr(usage, "input_tokens", 0) or 0) if usage else 0
            completion = int(getattr(usage, "output_tokens", 0) or 0) if usage else 0
            return response.content[0].text, (
                {
                    "prompt_tokens": prompt,
                    "completion_tokens": completion,
                    "total_tokens": prompt + completion,
                }
                if usage is not None
                else None
            ), ""

        return await self._run_completion(model, messages, kind, call)


class DeepSeekChatCompleter(_InstrumentedCompleterMixin):
    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self._client = client

    @property
    def provider(self) -> str:
        return "deepseek"

    @property
    def _openai_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )
        return self._client

    async def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        kind: str = "completion",
        **kwargs: Any,
    ) -> str:
        async def call() -> tuple[str, dict[str, int] | None, str]:
            response = await self._openai_client.chat.completions.create(
                model=model,
                messages=messages,
                **kwargs,
            )
            msg = response.choices[0].message
            text = getattr(msg, "content", None) or ""
            reasoning = getattr(msg, "reasoning_content", None) or ""
            if not text.strip():
                logger.warning(
                    "deepseek_empty_completion kind=%s model=%s finish_reason=%s "
                    "reasoning_content_len=%s reasoning_head=%r usage=%s",
                    kind,
                    model,
                    response.choices[0].finish_reason,
                    len(reasoning),
                    reasoning[:80],
                    response.usage,
                )
            usage = getattr(response, "usage", None)
            if usage is None:
                return text, None, reasoning
            return text, {
                "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(
                    getattr(usage, "completion_tokens", 0) or 0
                ),
                "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
                "cache_hit_tokens": int(
                    getattr(usage, "prompt_cache_hit_tokens", 0) or 0
                ),
                "cache_miss_tokens": int(
                    getattr(usage, "prompt_cache_miss_tokens", 0) or 0
                ),
            }, reasoning

        return await self._run_completion(model, messages, kind, call)


def create_chat_completer() -> LLMChatCompleter:
    if settings.llm_provider == "claude":
        return ClaudeChatCompleter()
    return DeepSeekChatCompleter()


__all__ = [
    "ClaudeChatCompleter",
    "DeepSeekChatCompleter",
    "LLMChatCompleter",
    "create_chat_completer",
]
