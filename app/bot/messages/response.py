from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChatProcessResult:
    action: str
    reason: str
    reply: str | None = None
    relevance_score: float = 0.0
