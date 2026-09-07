"""Add messages.channel and sender_display_name.

Revision ID: 011
Revises: 010
Create Date: 2026-09-07

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "channel",
            sa.String(),
            server_default="telegram",
            nullable=False,
        ),
    )
    op.add_column(
        "messages",
        sa.Column("sender_display_name", sa.String(length=255), nullable=True),
    )
    # PostgreSQL-legal DESC composite for channel-scoped session windows.
    op.create_index(
        "ix_messages_channel_created_at_id",
        "messages",
        [sa.text("channel"), sa.text("created_at DESC"), sa.text("id DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_messages_channel_created_at_id", table_name="messages")
    op.drop_column("messages", "sender_display_name")
    op.drop_column("messages", "channel")
