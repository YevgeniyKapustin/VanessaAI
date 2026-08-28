from pydantic import BaseModel, Field


class ChatImage(BaseModel):
    """One image attached to a message, as an OpenAI-compatible base64 data URL."""

    data_url: str = Field(min_length=1)
    mime_type: str = "image/jpeg"
    telegram_file_id: str | None = None


class ChatRequest(BaseModel):
    telegram_chat_id: int
    message: str = Field(min_length=1, max_length=4096)
    sender_telegram_id: int
    chat_title: str | None = None
    chat_type: str | None = None
    sender_username: str | None = None
    sender_first_name: str | None = None
    sender_last_name: str | None = None
    mentions_bot: bool = False
    reply_to_bot: bool = False
    reply_to_other_user: bool = False
    reply_to_sender_telegram_id: int | None = None
    reply_to_message_id: int | None = None
    reply_to_text: str | None = Field(default=None, max_length=4096)
    reply_to_sender_name: str | None = None
    # Images attached to this turn (vision). The bot downloads a Telegram photo
    # by file_id, encodes it to base64 and passes the data URL here.
    images: list[ChatImage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    action: str
    reason: str
    reply: str | None = None
    # The reply split into the individual Telegram messages to send (model-
    # marked 1-2 sentence blocks). Absent/empty = deliver ``reply`` as one
    # message. ``reply`` remains the marker-free full text.
    messages: list[str] | None = None
    context_count: int = 0
    relevance_score: float = 0.0
    sticker_tag: str | None = None
    # Telegram file_id of a photo to re-send (compose picked one from the album).
    photo_file_id: str | None = None
