import pytest

from app.config.settings import settings
from app.llm.providers import (
    ClaudeLLMProvider,
    DeepSeekLLMProvider,
    create_chat_completer,
    create_llm_provider,
)
from app.llm.providers.protocols import ClaudeChatCompleter, DeepSeekChatCompleter


class _FakeGeneration:
    """Generation that finalizes on exit (like Langfuse v4) and rejects late updates."""

    def __init__(self, sink: list) -> None:
        self._sink = sink
        self._closed = False

    def update(self, **kwargs) -> None:
        assert not self._closed, "update() called after the observation finalized"
        self._sink.append(kwargs)


class _FakeGenerationCM:
    def __init__(self, sink: list) -> None:
        self._sink = sink

    async def __aenter__(self) -> _FakeGeneration:
        self._gen = _FakeGeneration(self._sink)
        return self._gen

    async def __aexit__(self, *exc) -> bool:
        self._gen._closed = True
        return False


class _RecordingTracer:
    """Tracer that records generation output updates while the span is open."""

    def __init__(self) -> None:
        self.updates: list = []

    def generation(
        self,
        *,
        name: str,
        model=None,
        input=None,
        output=None,
        usage=None,
        metadata=None,
    ) -> _FakeGenerationCM:
        del name, model, input, output, usage, metadata
        return _FakeGenerationCM(self.updates)


@pytest.mark.asyncio
async def test_completer_records_generation_output_before_close(monkeypatch) -> None:
    """The completer (planner) generation must get its output while still open.

    Regression: ``_run_completion`` previously called ``gen.update(output=...)``
    AFTER the generation observation had closed, so Langfuse v4 (which finalizes
    on exit) dropped the planner's output — the final compose request showed
    output in the trace but the planner did not.
    """
    from app.llm.providers.protocols import _InstrumentedCompleterMixin

    class _FakeCompleter(_InstrumentedCompleterMixin):
        @property
        def provider(self) -> str:
            return "fake"

    async def call():
        return "planner json output", {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }

    tracer = _RecordingTracer()
    monkeypatch.setattr("app.llm.providers.protocols.get_tracer", lambda: tracer)

    text = await _FakeCompleter()._run_completion(
        "deepseek-chat",
        [{"role": "user", "content": "plan it"}],
        "planner",
        call,
    )
    assert text == "planner json output"
    assert tracer.updates == [
        {
            "output": "planner json output",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
    ]


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
