"""Tabella article_bookmarks (saved articles).

Una row per (user_id, article_id). PK composita per impedire duplicati e per
ordinare lookup "is bookmarked?" via index PK. Foreign key entrambi CASCADE
sulla delete (utente o articolo eliminato → bookmark rimosso senza orfani).

Revision ID: 0017_article_bookmarks
Revises: 0016_alerts_multi_topic
Create Date: 2026-05-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0017_article_bookmarks"
down_revision: str | Sequence[str] | None = "0016_alerts_multi_topic"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "article_bookmarks",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "article_id",
            sa.BigInteger(),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("user_id", "article_id", name="pk_article_bookmarks"),
    )
    # Index per la list per utente ordinata desc.
    op.create_index(
        "ix_article_bookmarks_user_created",
        "article_bookmarks",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_article_bookmarks_user_created", table_name="article_bookmarks")
    op.drop_table("article_bookmarks")
