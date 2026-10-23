from dataclasses import dataclass
from datetime import datetime
from typing import Any

from vanessa.core.messages_attachments import (
    ImageAttachment,
    attachments_from_dicts,
    attachments_to_dicts,
)

RAG_SOURCE_ROLE = "user"

__all__ = [
    "RAG_SOURCE_ROLE",
    "ContextBlock",
    "ContextMessage",
    "ImageAttachment",
    "PhotoCandidate",
    "StoredMessage",
    "WebResult",
    "attachments_from_dicts",
    "attachments_to_dicts",
    "context_block_message_count",
    "context_message_from_payload",
    "context_message_to_payload",
    "stored_block_to_context",
    "stored_to_context",
]


@dataclass(frozen=True, slots=True)
class ContextMessage:
    id: int
    role: str
    content: str
    sender_telegram_id: int | None = None
    sender_name: str | None = None
    created_at: datetime | None = None
    is_anchor: bool = False
    reply_to_message_id: int | None = None
    reply_to_text: str | None = None
    reply_to_sender_telegram_id: int | None = None
    reply_to_sender_name: str | None = None
    # Images attached to this message (vision turns / follow-up context).
    attachments: tuple[ImageAttachment, ...] = ()
    # Short generated label of the photo (photo_caption column) — lets a bare
    # photo be found by full-text search and rendered in the photo album.
    photo_caption: str | None = None


@dataclass(frozen=True, slots=True)
class PhotoCandidate:
    """One photo the bot could re-send, listed for the compose model.

    ``index`` is the stable [photo:<index>] reference the model may emit; the
    bot re-sends the photo via ``telegram_file_id``. ``data_url`` carries the
    stored bytes (base64) so the bot can fall back to an upload when the
    Telegram file_id is stale or expired — a stale file_id must not silently
    turn a "sent" claim into a lost photo.
    """

    index: int
    telegram_file_id: str | None
    caption: str
    sender_name: str | None = None
    created_at: datetime | None = None
    data_url: str | None = None


@dataclass(frozen=True, slots=True)
class WebResult:
    """A single live web-search hit injected into the compose prompt.

    ``title`` / ``snippet`` are plain text (the providers return clean snippets,
    not HTML), ready to be rendered verbatim into the prompt. ``published_date``
    is optional — Tavily returns it when the page has one; it helps the model
    judge freshness (e.g. "how old is this news item"). Defined here (core) so
    the LLM provider protocol can reference it without importing the web-search
    service package (avoids a core -> services import cycle).
    """

    title: str
    url: str
    snippet: str
    # ISO date when the provider exposes one (e.g. Tavily's published_date).
    published_date: str | None = None


@dataclass(frozen=True, slots=True)
class ContextBlock:
    anchor_id: int
    messages: tuple[ContextMessage, ...]


@dataclass(frozen=True, slots=True)
class StoredMessage:
    id: int
    role: str
    content: str
    sender_telegram_id: int | None = None
    qdrant_point_id: str | None = None
    telegram_message_id: int | None = None
    sender_name: str | None = None
    created_at: datetime | None = None
    reply_to_message_id: int | None = None
    reply_to_text: str | None = None
    reply_to_sender_telegram_id: int | None = None
    reply_to_sender_name: str | None = None
    # Raw attachment dicts from the DB ``attachments`` JSONB column; None when
    # the row has none. Converted to ``ImageAttachment`` by ``stored_to_context``.
    attachments: list[dict[str, Any]] | None = None
    # Short generated label of the photo (photo_caption column), full-text searchable.
    photo_caption: str | None = None
    channel: str = "telegram"


def stored_to_context(
    message: StoredMessage,
    *,
    is_anchor: bool = False,
) -> ContextMessage:
    return ContextMessage(
        id=message.id,
        role=message.role,
        content=message.content,
        sender_telegram_id=message.sender_telegram_id,
        sender_name=message.sender_name,
        created_at=message.created_at,
        is_anchor=is_anchor,
        reply_to_message_id=message.reply_to_message_id,
        reply_to_text=message.reply_to_text,
        reply_to_sender_telegram_id=message.reply_to_sender_telegram_id,
        reply_to_sender_name=message.reply_to_sender_name,
        attachments=attachments_from_dicts(message.attachments),
        photo_caption=message.photo_caption,
    )


def stored_block_to_context(
    anchor_id: int,
    messages: list[StoredMessage],
) -> ContextBlock | None:
    user_messages = [message for message in messages if message.role == RAG_SOURCE_ROLE]
    if not user_messages:
        return None
    anchor_id = next(
        (message.id for message in user_messages if message.id == anchor_id),
        user_messages[-1].id,
    )
    return ContextBlock(
        anchor_id=anchor_id,
        messages=tuple(
            stored_to_context(message, is_anchor=message.id == anchor_id)
            for message in user_messages
        ),
    )


def context_block_message_count(blocks: list[ContextBlock]) -> int:
    return sum(len(block.messages) for block in blocks)


def context_message_to_payload(message: ContextMessage) -> dict[str, Any]:
    created = message.created_at.isoformat() if message.created_at else None
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "sender_telegram_id": message.sender_telegram_id,
        "sender_name": message.sender_name,
        "created_at": created,
    }


def context_message_from_payload(data: dict[str, Any]) -> ContextMessage:
    raw_created = data.get("created_at")
    created_at = None
    if isinstance(raw_created, str) and raw_created:
        created_at = datetime.fromisoformat(raw_created)
    return ContextMessage(
        id=int(data["id"]),
        role=str(data.get("role") or "user"),
        content=str(data.get("content") or ""),
        sender_telegram_id=data.get("sender_telegram_id"),
        sender_name=data.get("sender_name"),
        created_at=created_at,
    )
