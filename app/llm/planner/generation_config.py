from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LLMGenerationParams:
    temperature: float
    top_p: float
    max_tokens: int
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0

    def to_anthropic_kwargs(self) -> dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
