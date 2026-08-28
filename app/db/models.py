from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


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
