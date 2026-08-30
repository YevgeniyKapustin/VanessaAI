from vanessa.config.settings import settings
from vanessa.core.protocols import LLMProviderProtocol
from vanessa.pipeline.llm.providers.claude import ClaudeLLMProvider
from vanessa.pipeline.llm.providers.deepseek import DeepSeekLLMProvider
from vanessa.pipeline.llm.providers.protocols import (
    ClaudeChatCompleter,
    DeepSeekChatCompleter,
    LLMChatCompleter,
    create_chat_completer,
)


def create_llm_provider() -> LLMProviderProtocol:
    if settings.llm_provider == "claude":
        return ClaudeLLMProvider()
    return DeepSeekLLMProvider()


__all__ = [
    "ClaudeChatCompleter",
    "ClaudeLLMProvider",
    "DeepSeekChatCompleter",
    "DeepSeekLLMProvider",
    "LLMChatCompleter",
    "create_chat_completer",
    "create_llm_provider",
]
