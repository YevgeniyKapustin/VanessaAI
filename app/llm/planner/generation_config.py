from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LLMGenerationParams:
    temperature: float
    top_p: float
    max_tokens: int
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    # Reasoning mode for models that support it. ``None`` (default) = the API's
    # normal mode — the parameter is NOT sent. Configured per stage in
    # config/content/llm.yaml (only the composer uses it — "high" for reply
    # quality); the planner deliberately leaves it unset so the gate stays fast,
    # and any stage that leaves it unset stays in the default normal mode and
    # the parameter never reaches the API.
    reasoning_effort: str | None = None

    def to_llm_kwargs(self) -> dict[str, Any]:
        """Sampling params shared by OpenAI-compatible (DeepSeek) and Claude APIs.

        ``reasoning_effort`` is only forwarded when explicitly configured, so
        stages that never set it stay in the default normal mode and the
        parameter never reaches the API.
        """
        kwargs: dict[str, Any] = {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        return kwargs
