"""Tabelle alerts + alert_matches (Phase 1.2.D).

Iteration-1: solo alert basati su topic (l'utente seleziona un topic curato
e riceve una notifica in-app quando un nuovo articolo lo contiene). Channels
è ARRAY estendibile per supportare 'push' in 1.2.E senza migration.

Schema:
- alerts(id, user_id, topic_id, channels, is_enabled, created_at, updated_at,
         UNIQUE (user_id, topic_id))
- alert_matches(alert_id, article_id, matched_at, PK composta)

Revision ID: 0014_alerts
Revises: 0013_notifications
Create Date: 2026-05-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0014_alerts"
down_revision: str | Sequence[str] | None = "0013_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "topic_id",
            sa.BigInteger(),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "channels",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY['inapp']::text[]"),
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "topic_id", name="uq_alerts_user_topic"),
    )
    op.create_index(
        "ix_alerts_topic_enabled",
        "alerts",
        ["topic_id"],
        postgresql_where=sa.text("is_enabled IS TRUE"),
    )

    op.create_table(
        "alert_matches",
        sa.Column(
            "alert_id",
            sa.BigInteger(),
            sa.ForeignKey("alerts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "article_id",
            sa.BigInteger(),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "matched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_alert_matches_article",
        "alert_matches",
        ["article_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_alert_matches_article", table_name="alert_matches")
    op.drop_table("alert_matches")
    op.drop_index("ix_alerts_topic_enabled", table_name="alerts")
    op.drop_table("alerts")
