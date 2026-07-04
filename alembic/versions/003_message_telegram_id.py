"""Add telegram_message_id for import deduplication

Revision ID: 003
Revises: 002
Create Date: 2026-07-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_messages_conversation_telegram_message_id",
        "messages",
        ["conversation_id", "telegram_message_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_messages_conversation_telegram_message_id",
        table_name="messages",
    )
    op.drop_column("messages", "telegram_message_id")
