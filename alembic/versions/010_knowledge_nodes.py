"""Add knowledge_nodes and knowledge_documents tables.

Revision ID: 010
Revises: 009
Create Date: 2026-08-29

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_nodes",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("folder", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "source_message_ids",
            postgresql.ARRAY(sa.BigInteger()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple'::regconfig, coalesce(title, '') || ' ' || "
                "coalesce(content, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_knowledge_aliases",
        "knowledge_nodes",
        ["aliases"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "idx_knowledge_meta",
        "knowledge_nodes",
        ["metadata"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index("idx_knowledge_type", "knowledge_nodes", ["type"], unique=False)
    op.create_index(
        "idx_knowledge_folder",
        "knowledge_nodes",
        ["folder"],
        unique=False,
    )
    op.create_index("idx_knowledge_slug", "knowledge_nodes", ["slug"], unique=False)
    op.create_index(
        "idx_knowledge_search",
        "knowledge_nodes",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_table(
        "knowledge_documents",
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("path"),
    )


def downgrade() -> None:
    op.drop_table("knowledge_documents")
    op.drop_index("idx_knowledge_search", table_name="knowledge_nodes")
    op.drop_index("idx_knowledge_slug", table_name="knowledge_nodes")
    op.drop_index("idx_knowledge_folder", table_name="knowledge_nodes")
    op.drop_index("idx_knowledge_type", table_name="knowledge_nodes")
    op.drop_index("idx_knowledge_meta", table_name="knowledge_nodes")
    op.drop_index("idx_knowledge_aliases", table_name="knowledge_nodes")
    op.drop_table("knowledge_nodes")
