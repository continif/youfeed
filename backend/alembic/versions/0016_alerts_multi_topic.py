"""Multi-topic alerts (Phase 1.2.D-ext).

Trasforma gli alert da 1:1 con un topic a M:N via tabella `alert_topics`,
con `alerts.match_mode` ('all'|'any') che decide se l'articolo deve
contenere TUTTI i topic dell'alert (AND) o ALMENO UNO (OR).

Schema dopo migration:
- alerts(id, user_id, channels[], match_mode, is_enabled, created_at, updated_at)
- alert_topics(alert_id, topic_id, PK composta, idx su topic_id)

Migration data: per ogni alert con `topic_id` non NULL viene popolata una
riga in alert_topics. Poi `alerts.topic_id` + UNIQUE(user_id, topic_id) +
partial index vengono droppati.

Revision ID: 0016_alerts_multi_topic
Revises: 0015_push_subscriptions
Create Date: 2026-05-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0016_alerts_multi_topic"
down_revision: str | Sequence[str] | None = "0015_push_subscriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Crea alert_topics
    op.create_table(
        "alert_topics",
        sa.Column(
            "alert_id",
            sa.BigInteger(),
            sa.ForeignKey("alerts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "topic_id",
            sa.BigInteger(),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index("ix_alert_topics_topic_id", "alert_topics", ["topic_id"])

    # 2. Aggiungi match_mode
    op.add_column(
        "alerts",
        sa.Column(
            "match_mode",
            sa.String(8),
            nullable=False,
            server_default=sa.text("'all'"),
        ),
    )
    op.create_check_constraint(
        "ck_alerts_match_mode",
        "alerts",
        "match_mode IN ('all', 'any')",
    )

    # 3. Migra dati: ogni alert.topic_id → riga in alert_topics
    op.execute(
        "INSERT INTO alert_topics(alert_id, topic_id) "
        "SELECT id, topic_id FROM alerts WHERE topic_id IS NOT NULL"
    )

    # 4. Drop constraint + colonna + indice partial vecchio
    op.drop_constraint("uq_alerts_user_topic", "alerts", type_="unique")
    op.drop_index("ix_alerts_topic_enabled", table_name="alerts")
    op.drop_column("alerts", "topic_id")

    # 5. Idx user_id per la list page
    op.create_index("ix_alerts_user_id", "alerts", ["user_id"])


def downgrade() -> None:
    # Aggiungi indietro topic_id, riempi col PRIMO topic di ogni alert
    op.drop_index("ix_alerts_user_id", table_name="alerts")
    op.add_column(
        "alerts",
        sa.Column("topic_id", sa.BigInteger(), nullable=True),
    )
    op.execute(
        "UPDATE alerts a SET topic_id = ("
        "  SELECT at.topic_id FROM alert_topics at "
        "  WHERE at.alert_id = a.id LIMIT 1"
        ")"
    )
    # NB: gli alert con > 1 topic in alert_topics perdono i topic extra.
    op.drop_constraint("ck_alerts_match_mode", "alerts", type_="check")
    op.drop_column("alerts", "match_mode")
    op.create_index(
        "ix_alerts_topic_enabled",
        "alerts",
        ["topic_id"],
        postgresql_where=sa.text("is_enabled IS TRUE"),
    )
    op.create_unique_constraint(
        "uq_alerts_user_topic", "alerts", ["user_id", "topic_id"]
    )
    op.drop_index("ix_alert_topics_topic_id", table_name="alert_topics")
    op.drop_table("alert_topics")
