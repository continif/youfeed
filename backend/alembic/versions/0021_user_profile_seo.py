"""Colonne profile_seo_title / profile_seo_description sui users.

Permettono all'utente di personalizzare il `<title>` e la `<meta description>`
della propria pagina pubblica `/{username}`. NULL = default markettaro.

Revision ID: 0021_user_profile_seo
Revises: 0020_traffic_blocks_ip_ua
Create Date: 2026-05-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0021_user_profile_seo"
down_revision: str | Sequence[str] | None = "0020_traffic_blocks_ip_ua"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("profile_seo_title", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("profile_seo_description", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "profile_seo_description")
    op.drop_column("users", "profile_seo_title")
