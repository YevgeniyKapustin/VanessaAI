from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LLMGenerationParams:
    temperature: float
    top_p: float
    max_tokens: int
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0

    def to_llm_kwargs(self) -> dict[str, Any]:
        """Sampling params shared by OpenAI-compatible (DeepSeek) and Claude APIs."""
        return {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
