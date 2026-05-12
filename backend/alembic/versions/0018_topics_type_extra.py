"""Estende `topics.type` con nuovi tipi inferibili da Wikidata P31.

Aggiunge: company, software, hardware, organization, event, work.

- company:    distinzione lecitamente dal "brand" (Apple Inc. = company,
              Apple = brand). Utile per relazioni `owned_by` ecc.
- software:   programmi/app/OS (Linux, Photoshop, ChatGPT)
- hardware:   dispositivi/componenti hardware non riconducibili a un model
              specifico (iPhone 15 = model, "smartphone" = hardware)
- organization: enti non-profit, ONG, istituzioni pubbliche distinte da
              company (Croce Rossa, ONU)
- event:      eventi storici/fiere/elezioni (G20, EXPO 2025)
- work:       libri, film, opere d'arte, programmi TV

Revision ID: 0018_topics_type_extra
Revises: 0017_article_bookmarks
Create Date: 2026-05-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0018_topics_type_extra"
down_revision: str | Sequence[str] | None = "0017_article_bookmarks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TYPES_NEW = (
    "brand",
    "person",
    "subject",
    "location",
    "model",
    "invalid",
    "company",
    "software",
    "hardware",
    "organization",
    "event",
    "work",
)
_TYPES_OLD = (
    "brand",
    "person",
    "subject",
    "location",
    "model",
    "invalid",
)


def _check_expr(types: tuple[str, ...]) -> str:
    inside = ",".join(f"'{t}'" for t in types)
    return f"type IN ({inside})"


def upgrade() -> None:
    op.drop_constraint("ck_topics_type", "topics", type_="check")
    op.create_check_constraint("ck_topics_type", "topics", _check_expr(_TYPES_NEW))


def downgrade() -> None:
    # Re-assegna i topic con type estesi a 'subject' (fallback safe) prima
    # di restringere il check, altrimenti il vincolo fallirebbe.
    op.execute(
        "UPDATE topics SET type='subject' WHERE type IN ("
        "'company','software','hardware','organization','event','work')"
    )
    op.drop_constraint("ck_topics_type", "topics", type_="check")
    op.create_check_constraint("ck_topics_type", "topics", _check_expr(_TYPES_OLD))
