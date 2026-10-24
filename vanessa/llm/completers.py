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
from vanessa.infrastructure.observability.trace_log.llm import trace_llm_call
from vanessa.infrastructure.observability.tracing import get_tracer
from vanessa.llm.usage import anthropic_usage, openai_usage

logger = logging.getLogger(__name__)


async def run_instrumented_completion(
    provider: str,
    model: str,
    messages: list[dict[str, Any]],
    kind: str,
    call,
) -> str:
    """Shared metrics/tracing around a single chat completion."""
    started = time.perf_counter()
    tracer = get_tracer()
    async with tracer.generation(
        name=f"llm_{kind}",
        model=model,
        input=messages,
        metadata={"provider": provider, "kind": kind},
    ) as gen:
        try:
            text, usage, reasoning = await call()
        except Exception as exc:
            record_llm_call(
                provider=provider,
                model=model,
                kind=kind,
                started=started,
                status="error",
                error_type=classify_llm_error(exc),
            )
            trace_llm_call(
                provider=provider,
                model=model,
                kind=kind,
                messages=messages,
                error=type(exc).__name__,
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
        provider=provider,
        model=model,
        kind=kind,
        started=started,
        status="success",
        usage=usage,
        output=text,
    )
    trace_llm_call(
        provider=provider,
        model=model,
        kind=kind,
        messages=messages,
        output=text,
        reasoning=reasoning,
        usage=usage,
    )
    return text


class ClaudeChatCompleter:
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
            # The Anthropic API requires max_tokens: an "off" config uses the setting.
            kwargs.setdefault("max_tokens", settings.anthropic_max_tokens)
            response = await self._client.messages.create(
                model=model,
                messages=messages,
                **kwargs,
            )
            return response.content[0].text, anthropic_usage(response), ""

        return await run_instrumented_completion(
            self.provider, model, messages, kind, call
        )


class DeepSeekChatCompleter:
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
            return text, openai_usage(response), reasoning

        return await run_instrumented_completion(
            self.provider, model, messages, kind, call
        )


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
