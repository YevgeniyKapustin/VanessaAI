"""Add photo caption to messages

Revision ID: 008
Revises: 007
Create Date: 2026-08-28

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Short generated label of a photo message (vision captioner). Included in
    # the FTS search_vector so a bare photo is findable "by meaning" in RAG.
    op.add_column(
        "messages",
        sa.Column("photo_caption", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "photo_caption")
