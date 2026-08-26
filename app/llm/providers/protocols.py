from typing import Any, Protocol

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.config.settings import settings


class LLMChatCompleter(Protocol):
    """Single-turn chat completion shared by the turn planner across providers."""

    async def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> str: ...


class ClaudeChatCompleter:
    def __init__(self, client: AsyncAnthropic | None = None) -> None:
        self._client = client or AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        response = await self._client.messages.create(
            model=model,
            messages=messages,
            **kwargs,
        )
        return response.content[0].text


class DeepSeekChatCompleter:
    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self._client = client

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
        **kwargs: Any,
    ) -> str:
        response = await self._openai_client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs,
        )
        return response.choices[0].message.content or ""


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
