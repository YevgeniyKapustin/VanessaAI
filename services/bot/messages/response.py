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
    # Telegram file_id of a photo to re-send (compose picked one from the album).
    photo_file_id: str | None = None
    # Base64 data URL of the same photo (stored bytes) — fallback source for an
    # upload when the Telegram file_id is stale at delivery time.
    photo_data_url: str | None = None
