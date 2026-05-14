"""Tabelle blocked_ips (con expires_at) + blocked_user_agents.

`blocked_ips` ha un `expires_at` nullable: permanente se NULL, scaduto se
in passato. Le righe scadute restano in tabella e vengono ignorate dalla
cache + filtrate da un cron di cleanup (vedi retention_sweep).

`blocked_user_agents` contiene pattern substring case-insensitive da
matchare con `in user_agent.lower()` (semplice, niente regex per evitare
ReDoS).

Revision ID: 0020_traffic_blocks_ip_ua
Revises: 0019_traffic_blocks
Create Date: 2026-05-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0020_traffic_blocks_ip_ua"
down_revision: str | Sequence[str] | None = "0019_traffic_blocks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "blocked_ips",
        sa.Column("ip", sa.Text(), primary_key=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_blocked_ips_expires_at", "blocked_ips", ["expires_at"]
    )
    op.create_table(
        "blocked_user_agents",
        sa.Column("pattern", sa.Text(), primary_key=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("blocked_user_agents")
    op.drop_index("ix_blocked_ips_expires_at", table_name="blocked_ips")
    op.drop_table("blocked_ips")
