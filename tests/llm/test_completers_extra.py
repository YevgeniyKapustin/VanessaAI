from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from vanessa.llm.completers import (
    ClaudeChatCompleter,
    DeepSeekChatCompleter,
    create_chat_completer,
    run_instrumented_completion,
)


class _Gen:
    def __init__(self) -> None:
        self.updated = None

    def update(self, **kwargs) -> None:
        self.updated = kwargs


class _CM:
    async def __aenter__(self) -> _Gen:
        self.gen = _Gen()
        return self.gen

    async def __aexit__(self, *exc) -> bool:
        return False


async def test_instrumented_completion_success_and_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "vanessa.llm.completers.get_tracer",
        lambda: SimpleNamespace(generation=lambda **_k: _CM()),
    )
    recorded: list[dict] = []
    monkeypatch.setattr(
        "vanessa.llm.completers.record_llm_call",
        lambda **kwargs: recorded.append(kwargs),
    )

    async def call():
        return "ok", {"prompt_tokens": 1}, "think"

    text = await run_instrumented_completion("deepseek", "m", [], "k", call)
    assert text == "ok"

    async def boom():
        raise RuntimeError("down")

    with suppress(RuntimeError):
        await run_instrumented_completion("deepseek", "m", [], "k", boom)
    assert any(item.get("status") == "error" for item in recorded)


async def test_deepseek_and_claude_completers(monkeypatch) -> None:
    monkeypatch.setattr(
        "vanessa.llm.completers.get_tracer",
        lambda: SimpleNamespace(generation=lambda **_k: _CM()),
    )
    monkeypatch.setattr("vanessa.llm.completers.record_llm_call", lambda **_k: None)

    choice = MagicMock()
    choice.message.content = "hi"
    choice.message.reasoning_content = "why"
    choice.finish_reason = "stop"
    response = MagicMock()
    response.choices = [choice]
    response.usage = SimpleNamespace(
        prompt_tokens=1,
        completion_tokens=2,
        total_tokens=3,
        prompt_cache_hit_tokens=0,
        prompt_cache_miss_tokens=1,
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    deep = DeepSeekChatCompleter(client=client)
    assert deep.provider == "deepseek"
    assert await deep.complete("m", [{"role": "user", "content": "q"}]) == "hi"

    empty_choice = MagicMock()
    empty_choice.message.content = ""
    empty_choice.message.reasoning_content = ""
    empty_choice.finish_reason = "length"
    empty = MagicMock()
    empty.choices = [empty_choice]
    empty.usage = None
    client.chat.completions.create = AsyncMock(return_value=empty)
    assert await deep.complete("m", []) == ""

    claude_resp = SimpleNamespace(
        content=[SimpleNamespace(text="yo")],
        usage=SimpleNamespace(input_tokens=1, output_tokens=2),
    )
    claude_client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(return_value=claude_resp))
    )
    claude = ClaudeChatCompleter(client=claude_client)
    assert claude.provider == "claude"
    assert await claude.complete("m", [], reasoning_effort="x") == "yo"


def test_create_chat_completer_branches(monkeypatch) -> None:
    monkeypatch.setattr("vanessa.llm.completers.settings.llm_provider", "claude")
    assert isinstance(create_chat_completer(), ClaudeChatCompleter)
    monkeypatch.setattr("vanessa.llm.completers.settings.llm_provider", "deepseek")
    assert isinstance(create_chat_completer(), DeepSeekChatCompleter)
