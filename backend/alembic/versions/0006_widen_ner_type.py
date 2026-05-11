"""widen entities.ner_type to varchar(32)

I valori da regex extractor (REGEX_BRAND_ALPHA, REGEX_BRAND_SINGLE) eccedono
i 16 caratteri originali.

Revision ID: 0006_widen_ner_type
Revises: 0005_entity_source_counts
Create Date: 2026-05-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0006_widen_ner_type"
down_revision: str | Sequence[str] | None = "0005_entity_source_counts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "entities",
        "ner_type",
        existing_type=sa.String(16),
        type_=sa.String(32),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "entities",
        "ner_type",
        existing_type=sa.String(32),
        type_=sa.String(16),
        existing_nullable=False,
    )
