from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Computed,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from vanessa.infrastructure.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    nickname: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sender_telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    reply_to_message_id: Mapped[int | None] = mapped_column(BigInteger)
    reply_to_text: Mapped[str | None] = mapped_column(Text)
    reply_to_sender_telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    reply_to_sender_name: Mapped[str | None] = mapped_column(String(255))
    # Images attached to this message (vision turns): list of
    # {data_url, mime_type, telegram_file_id} dicts (base64 data URLs).
    attachments: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    # Short generated label of a photo message (vision captioner); included in
    # the FTS search_vector so a bare photo is findable "by meaning" in RAG.
    photo_caption: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_messages_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_messages_created_at", "created_at"),
        Index("ix_messages_telegram_message_id", "telegram_message_id"),
    )


class OutboxEvent(Base):
    """Transactional outbox: broker publish that is atomic with a DB write.

    A producer inserts a row in the SAME transaction as its domain writes; the
    relay worker later publishes it to the broker and marks it delivered. This
    eliminates the dual-write inconsistency (DB updated but event never sent).
    """

    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Target stream (e.g. "tasks").
    stream: Mapped[str] = mapped_column(String(128), nullable=False)
    # Broker message kind, for observability / debugging.
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Serialized stream-field map (see vanessa.infrastructure.broker.serialization.encode).
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # pending → delivered | failed
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_outbox_events_status_id", "status", "id"),
    )


class KnowledgeNodeRow(Base):
    """One knowledge-vault document (person card, event, lore, culture, log)."""

    __tablename__ = "knowledge_nodes"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    folder: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    slug: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'"),
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_message_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger),
        nullable=False,
        server_default=text("'{}'"),
    )
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple'::regconfig, coalesce(title, '') || ' ' || "
            "coalesce(content, ''))",
            persisted=True,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_knowledge_aliases", "aliases", postgresql_using="gin"),
        Index("idx_knowledge_meta", "metadata", postgresql_using="gin"),
        Index("idx_knowledge_type", "type"),
        Index("idx_knowledge_folder", "folder"),
        Index("idx_knowledge_slug", "slug"),
        Index("idx_knowledge_search", "search_vector", postgresql_using="gin"),
    )


class KnowledgeDocument(Base):
    """YAML-like vault documents: folder indexes and sweep state."""

    __tablename__ = "knowledge_documents"

    path: Mapped[str] = mapped_column(String(512), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
