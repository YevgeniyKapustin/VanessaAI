from app.config.settings import settings
from app.core.protocols import LLMProviderProtocol
from app.llm.providers.claude import ClaudeLLMProvider
from app.llm.providers.deepseek import DeepSeekLLMProvider
from app.llm.providers.protocols import (
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
