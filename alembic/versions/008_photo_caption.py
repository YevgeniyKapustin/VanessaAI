"""Add photo caption to messages

Revision ID: 008
Revises: 007
Create Date: 2026-08-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Short generated label of a photo message (vision captioner). Included in
    # the FTS search_vector so a bare photo is findable "by meaning" in RAG.
    op.add_column(
        "messages",
        sa.Column("photo_caption", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "photo_caption")
