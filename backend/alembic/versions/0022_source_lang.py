"""Colonna `sources.lang`: lingua rilevata della fonte.

Le fonti non italiane restano visibili a chi le ha aggiunte ma vengono
escluse dall'engine (topic, ricerca pubblica, vetrina). NULL = non ancora
rilevata (trattata come italiana). Il backfill delle fonti esistenti si fa
con `python -m app.utils.backfill_source_lang`.

Revision ID: 0022_source_lang
Revises: 0021_user_profile_seo
Create Date: 2026-10-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0022_source_lang"
down_revision: str | Sequence[str] | None = "0021_user_profile_seo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("lang", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("sources", "lang")
