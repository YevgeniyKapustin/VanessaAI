"""Drop conversations — single global message context

Revision ID: 004
Revises: 003
Create Date: 2026-07-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        "ix_messages_conversation_telegram_message_id",
        table_name="messages",
    )
    op.drop_index("ix_messages_conversation_id_created_at", table_name="messages")
    op.drop_constraint("messages_conversation_id_fkey", "messages", type_="foreignkey")
    op.drop_column("messages", "conversation_id")
    op.drop_table("conversations")
    op.create_index("ix_messages_created_at", "messages", ["created_at"])
    op.create_index(
        "ix_messages_telegram_message_id",
        "messages",
        ["telegram_message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_messages_telegram_message_id", table_name="messages")
    op.drop_index("ix_messages_created_at", table_name="messages")
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("chat_type", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_chat_id"),
    )
    op.add_column(
        "messages",
        sa.Column("conversation_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "messages_conversation_id_fkey",
        "messages",
        "conversations",
        ["conversation_id"],
        ["id"],
    )
    op.alter_column("messages", "conversation_id", nullable=False)
    op.create_index(
        "ix_messages_conversation_id_created_at",
        "messages",
        ["conversation_id", "created_at"],
    )
    op.create_index(
        "ix_messages_conversation_telegram_message_id",
        "messages",
        ["conversation_id", "telegram_message_id"],
        unique=True,
    )
