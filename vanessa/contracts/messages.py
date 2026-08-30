"""Versioned wire contracts shared across VanessaAI services.

These pydantic models are the ONLY thing services exchange over the broker —
a service never imports another service's runtime code. Every message is
self-describing (``schema_version``, ``kind``, ``message_id``,
``correlation_id``) so consumers can validate, deduplicate and correlate
without any shared process state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, ClassVar
from uuid import uuid4

from pydantic import BaseModel, Field

from vanessa.contracts.version import SCHEMA_VERSION

__all__ = [
    "SCHEMA_VERSION",
    "BrokerMessage",
    "TurnImage",
    "TurnRequest",
    "TurnStarted",
    "TurnReply",
    "TaskKind",
    "TaskMessage",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class BrokerMessage(BaseModel):
    """Base class for every message that crosses the broker."""

    #: Stable wire kind, unique per message type (overridden in subclasses).
    kind: ClassVar[str]

    schema_version: int = SCHEMA_VERSION
    #: Unique per logical message; consumers use it for at-least-once dedup.
    message_id: str = Field(default_factory=new_id)
    #: Links a request to its replies (RPC); doubles as the transport request id.
    correlation_id: str = Field(default_factory=new_id)
    #: UTC timestamp the producer created the message.
    timestamp: datetime = Field(default_factory=_utcnow)
    #: Distributed-trace id propagated across hops (OTel / Langfuse).
    trace_id: str | None = None
    #: For RPC: the stream the responder must publish its reply to.
    reply_to: str | None = None

    @classmethod
    def message_kind(cls) -> str:
        return cls.kind


class TurnImage(BaseModel):
    """One image attached to a turn (OpenAI-compatible base64 data URL)."""

    data_url: str = Field(min_length=1)
    mime_type: str = "image/jpeg"
    telegram_file_id: str | None = None


class TurnRequest(BrokerMessage):
    """A user message forwarded from the transport (bot) to the agent core.

    Mirrors the HTTP ``ChatRequest`` payload so both transports are
    interchangeable.
    """

    kind: ClassVar[str] = "turn_request"

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
    images: list[TurnImage] = Field(default_factory=list)


class TurnStarted(BrokerMessage):
    """Emitted by the agent core the moment the decision gate passes.

    The transport (bot) uses it to switch the chat action to "typing..."
    while the real answer is composed — mirrors the HTTP SSE ``started`` event.
    """

    kind: ClassVar[str] = "turn_started"


class TurnReply(BrokerMessage):
    """The agent core's final answer for a turn (mirrors ``ChatResponse``)."""

    kind: ClassVar[str] = "turn_reply"

    action: str
    reason: str
    reply: str | None = None
    messages: list[str] | None = None
    context_count: int = 0
    relevance_score: float = 0.0
    sticker_tag: str | None = None
    photo_file_id: str | None = None
    photo_data_url: str | None = None


class TaskKind(StrEnum):
    """Fire-and-forget background task types consumed by the worker service."""

    INDEX_MESSAGE = "index_message"
    SWEEP = "sweep"
    PORTRAIT = "portrait"
    MEMORY_EXTRACT = "memory_extract"
    METRICS_SNAPSHOT = "metrics_snapshot"
    PHOTO_CAPTION = "photo_caption"
    VECTOR_INDEX = "vector_index"
    REINDEX_KNOWLEDGE = "reindex_knowledge"


class TaskMessage(BrokerMessage):
    """A fire-and-forget background task for the worker service."""

    kind: ClassVar[str] = "task"

    task: TaskKind
    #: JSON-safe payload; its schema depends on ``task``.
    payload: dict[str, Any] = Field(default_factory=dict)
    #: Optional explicit dedup key (e.g. the message id for indexing).
    dedup_key: str | None = None
