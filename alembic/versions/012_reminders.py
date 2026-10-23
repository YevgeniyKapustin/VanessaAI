"""Add reminders table (scheduled chat posts).

Revision ID: 012
Revises: 011
Create Date: 2026-10-24

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reminders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "channel",
            sa.String(length=16),
            server_default="telegram",
            nullable=False,
        ),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "cron",
            sa.String(length=64),
            server_default="",
            nullable=False,
        ),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reminders_next_run_at", "reminders", ["next_run_at"], unique=False
    )
    op.create_index("ix_reminders_chat_id", "reminders", ["chat_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_reminders_chat_id", table_name="reminders")
    op.drop_index("ix_reminders_next_run_at", table_name="reminders")
    op.drop_table("reminders")
