"""conversation context schema

Revision ID: 002
Revises: 001
Create Date: 2026-07-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
    op.add_column("messages", sa.Column("conversation_id", sa.Integer(), nullable=True))
    op.add_column(
        "messages",
        sa.Column("sender_telegram_id", sa.BigInteger(), nullable=True),
    )
    op.drop_index("ix_messages_user_id_created_at", table_name="messages")
    op.drop_constraint("messages_user_id_fkey", "messages", type_="foreignkey")
    op.drop_column("messages", "user_id")
    op.alter_column("messages", "conversation_id", nullable=False)
    op.create_foreign_key(
        "messages_conversation_id_fkey",
        "messages",
        "conversations",
        ["conversation_id"],
        ["id"],
    )
    op.create_index(
        "ix_messages_conversation_id_created_at",
        "messages",
        ["conversation_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_id_created_at", table_name="messages")
    op.drop_constraint("messages_conversation_id_fkey", "messages", type_="foreignkey")
    op.add_column("messages", sa.Column("user_id", sa.Integer(), nullable=True))
    op.drop_column("messages", "sender_telegram_id")
    op.drop_column("messages", "conversation_id")
    op.create_foreign_key(
        "messages_user_id_fkey",
        "messages",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_index(
        "ix_messages_user_id_created_at",
        "messages",
        ["user_id", "created_at"],
        unique=False,
    )
    op.drop_table("conversations")
