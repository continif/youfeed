"""Estendi article_topics.source per accettare 'composite'.

Permette ai topic sintetici prodotti dalle composite-rules di classify
(es. google + gemini → google-gemini) di essere persistiti in article_topics.

Revision ID: 0008_article_topics_composite_source
Revises: 0007_topics_type_extended
Create Date: 2026-05-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0008_at_composite_source"
down_revision: str | Sequence[str] | None = "0007_topics_type_extended"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_article_topics_source",
        "article_topics",
        type_="check",
    )
    op.create_check_constraint(
        "ck_article_topics_source",
        "article_topics",
        "source IN ('dict', 'ner', 'regex', 'taxonomy', 'llm', 'composite')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_article_topics_source",
        "article_topics",
        type_="check",
    )
    op.create_check_constraint(
        "ck_article_topics_source",
        "article_topics",
        "source IN ('dict', 'ner', 'regex', 'taxonomy', 'llm')",
    )
