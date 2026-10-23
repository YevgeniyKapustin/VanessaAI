from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LLMGenerationParams:
    temperature: float
    top_p: float
    # None or 0 = off: the parameter is not sent, the API uses its model default.
    max_tokens: int | None
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    reasoning_effort: str | None = None

    def to_llm_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"temperature": self.temperature}
        if self.max_tokens:
            kwargs["max_tokens"] = self.max_tokens
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        return kwargs
