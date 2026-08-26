import pytest

from app.config.settings import settings
from app.llm.providers import (
    ClaudeLLMProvider,
    DeepSeekLLMProvider,
    create_chat_completer,
    create_llm_provider,
)
from app.llm.providers.protocols import ClaudeChatCompleter, DeepSeekChatCompleter


@pytest.mark.parametrize(
    "provider_setting, expected",
    [
        ("deepseek", DeepSeekLLMProvider),
        ("claude", ClaudeLLMProvider),
    ],
)
def test_create_llm_provider_selects_backend(
    provider_setting: str,
    expected: type,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "llm_provider", provider_setting)
    provider = create_llm_provider()
    assert isinstance(provider, expected)


@pytest.mark.parametrize(
    "provider_setting, expected",
    [
        ("deepseek", DeepSeekChatCompleter),
        ("claude", ClaudeChatCompleter),
    ],
)
def test_create_chat_completer_selects_backend(
    provider_setting: str,
    expected: type,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "llm_provider", provider_setting)
    completer = create_chat_completer()
    assert isinstance(completer, expected)
