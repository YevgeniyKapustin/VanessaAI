"""Add attachments to messages

Revision ID: 007
Revises: 006
Create Date: 2026-08-28

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Images attached to a message (vision turns): list of
    # {data_url, mime_type, telegram_file_id} dicts (base64 data URLs).
    op.add_column(
        "messages",
        sa.Column("attachments", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "attachments")
