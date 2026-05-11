"""entity_source_counts: per-source frequency per entity

Revision ID: 0005_entity_source_counts
Revises: 0004_activity_log
Create Date: 2026-05-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0005_entity_source_counts"
down_revision: str | Sequence[str] | None = "0004_activity_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entity_source_counts",
        sa.Column(
            "entity_id",
            sa.BigInteger(),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.BigInteger(),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("entity_id", "source_id", name="pk_entity_source_counts"),
    )
    op.create_index(
        "ix_entity_source_counts_entity",
        "entity_source_counts",
        ["entity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_entity_source_counts_entity", table_name="entity_source_counts")
    op.drop_table("entity_source_counts")
