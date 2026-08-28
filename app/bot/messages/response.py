from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChatProcessResult:
    action: str
    reason: str
    reply: str | None = None
    # The reply split into the individual Telegram messages to send (model-
    # marked 1-2 sentence blocks). None/empty = send ``reply`` as one message.
    messages: list[str] | None = None
    relevance_score: float = 0.0
    sticker_tag: str | None = None
