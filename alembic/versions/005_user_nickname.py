"""Add nickname to users

Revision ID: 005
Revises: 004
Create Date: 2026-07-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("nickname", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "nickname")
