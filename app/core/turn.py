from dataclasses import dataclass

from app.core.messages import ImageAttachment


@dataclass(frozen=True, slots=True)
class ChatTurnInput:
    telegram_chat_id: int
    message: str
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
    reply_to_text: str | None = None
    reply_to_sender_name: str | None = None
    # Images attached to this turn (vision). Empty for plain text turns.
    images: tuple[ImageAttachment, ...] = ()

    @property
    def has_image(self) -> bool:
        return bool(self.images)


@dataclass(frozen=True, slots=True)
class ConversationTurnResult:
    action: str
    reason: str
    reply: str | None = None
    # The reply split into the individual Telegram messages to send (1-2
    # sentence blocks, model-marked with the block marker). ``None``/empty means
    # the whole ``reply`` is delivered as a single message. ``reply`` stays the
    # marker-free full text (stored in the DB, used for metrics).
    messages: list[str] | None = None
    context_count: int = 0
    relevance_score: float = 0.0
    sticker_tag: str | None = None
    # Telegram file_id of a photo the bot should re-send (compose model picked
    # one from the photo album via the [photo:<index>] marker).
    photo_file_id: str | None = None
    # Base64 data URL of the same photo (the stored bytes) — lets the bot fall
    # back to an upload when the Telegram file_id is stale at delivery time.
    photo_data_url: str | None = None
