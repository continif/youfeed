"""Estendi i valori accettati di topics.type a ('brand','person','subject','location','model').

Revision ID: 0007_topics_type_extended
Revises: 0006_widen_ner_type
Create Date: 2026-05-07
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0007_topics_type_extended"
down_revision: str | Sequence[str] | None = "0006_widen_ner_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_topics_type", "topics", type_="check")
    op.create_check_constraint(
        "ck_topics_type",
        "topics",
        "type IN ('brand','person','subject','location','model')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_topics_type", "topics", type_="check")
    op.create_check_constraint(
        "ck_topics_type",
        "topics",
        "type IN ('brand','person','subject')",
    )
