"""Tabelle blocked_countries + blocked_asns (traffic block config).

Liste piccole (decine di righe) gestite dall'admin via /yf_admin/security/blocks.
Il middleware TrafficBlockMiddleware le legge in memoria e refresha ogni 60s.

Revision ID: 0019_traffic_blocks
Revises: 0018_topics_type_extra
Create Date: 2026-05-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0019_traffic_blocks"
down_revision: str | Sequence[str] | None = "0018_topics_type_extra"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "blocked_countries",
        sa.Column("iso_code", sa.CHAR(2), primary_key=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_table(
        "blocked_asns",
        sa.Column("asn", sa.BigInteger(), primary_key=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("blocked_asns")
    op.drop_table("blocked_countries")
