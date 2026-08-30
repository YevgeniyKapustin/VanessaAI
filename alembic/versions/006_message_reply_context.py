"""Add reply context to messages

Revision ID: 006
Revises: 005
Create Date: 2026-08-26

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("reply_to_message_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("reply_to_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("reply_to_sender_telegram_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("reply_to_sender_name", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "reply_to_sender_name")
    op.drop_column("messages", "reply_to_sender_telegram_id")
    op.drop_column("messages", "reply_to_text")
    op.drop_column("messages", "reply_to_message_id")
