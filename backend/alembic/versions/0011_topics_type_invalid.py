"""Aggiungi 'invalid' ai valori accettati di topics.type.

Permette di marcare topic come "non validi" senza cancellarli, così l'extractor
auto-extracted non li ricrea: l'on_conflict_do_nothing su slug + check del tipo
risolve il caso in cui lo stesso surface_form arriverebbe di nuovo dal NER.

Revision ID: 0011_topics_type_invalid
Revises: 0010_topic_rules_reconcile
Create Date: 2026-05-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0011_topics_type_invalid"
down_revision: str | Sequence[str] | None = "0010_topic_rules_reconcile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_topics_type", "topics", type_="check")
    op.create_check_constraint(
        "ck_topics_type",
        "topics",
        "type IN ('brand','person','subject','location','model','invalid')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_topics_type", "topics", type_="check")
    op.create_check_constraint(
        "ck_topics_type",
        "topics",
        "type IN ('brand','person','subject','location','model')",
    )
