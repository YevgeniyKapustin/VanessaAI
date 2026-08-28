"""Add attachments to messages

Revision ID: 007
Revises: 006
Create Date: 2026-08-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Images attached to a message (vision turns): list of
    # {data_url, mime_type, telegram_file_id} dicts (base64 data URLs).
    op.add_column(
        "messages",
        sa.Column("attachments", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "attachments")
