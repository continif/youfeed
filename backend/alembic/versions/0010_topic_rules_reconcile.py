"""Riconcilia topic_term_rules con i set Python in classify/extractor.

Migration 0009 ha seedato un sottoinsieme dei termini hardcoded (alcuni
round successivi — Mira/Alto/Posta — non erano nel migration file ma erano
nei moduli Python). Questa migration inserisce tutti i termini correnti
con `ON CONFLICT DO NOTHING` per allineamento idempotente.

Se in futuro l'admin aggiunge/elimina rule via UI, questa migration NON
le tocca (insert ON CONFLICT — i record esistenti restano).

Revision ID: 0010_topic_rules_reconcile
Revises: 0009_topic_rules_tables
Create Date: 2026-05-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0010_topic_rules_reconcile"
down_revision: str | Sequence[str] | None = "0009_topic_rules_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Importa i set hardcoded dai moduli Python: questi sono la fonte di
    # verità al momento di applicare la migration. Idempotente per design.
    from app.ingestion.classify import (  # noqa: PLC0415
        _AMBIGUOUS_LOCATION_TERMS,
        _CASE_SENSITIVE_SLUGS,
    )
    from app.topic_extractor.extractor import _BRAND_SINGLE_BLACKLIST  # noqa: PLC0415

    bind = op.get_bind()
    rows = (
        [{"kind": "ambiguous_location", "term": t} for t in _AMBIGUOUS_LOCATION_TERMS]
        + [{"kind": "brand_single", "term": t} for t in _BRAND_SINGLE_BLACKLIST]
        + [{"kind": "case_sensitive_slug", "term": t} for t in _CASE_SENSITIVE_SLUGS]
    )
    if rows:
        bind.execute(
            sa.text(
                "INSERT INTO topic_term_rules (kind, term) "
                "VALUES (:kind, :term) ON CONFLICT (kind, term) DO NOTHING"
            ),
            rows,
        )


def downgrade() -> None:
    # No-op: non sappiamo quali term erano stati aggiunti da questa migration
    # vs da 0009 vs dall'admin via UI. Downgrade lascia tutto.
    pass
