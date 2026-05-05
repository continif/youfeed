"""sources, categories, user_sources, featured_sources

Revision ID: 0002_sources_categories
Revises: 0001_users_auth
Create Date: 2026-05-05

"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_sources_categories"
down_revision: str | Sequence[str] | None = "0001_users_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("url_site", sa.Text(), nullable=True),
        sa.Column("url_feed", sa.Text(), nullable=True),
        sa.Column("wp_api_root", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("favicon_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("poll_interval", sa.Integer(), nullable=False, server_default=sa.text("1800")),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("last_modified", sa.Text(), nullable=True),
        sa.Column("qualified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discovery_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("url_feed", name="uq_sources_url_feed"),
        sa.UniqueConstraint("wp_api_root", name="uq_sources_wp_api_root"),
        sa.CheckConstraint(
            "kind IN ('rss', 'wordpress_api', 'invalid')", name="ck_sources_kind"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'broken', 'paused')", name="ck_sources_status"
        ),
    )
    op.create_index("ix_sources_status", "sources", ["status"])
    op.create_index("ix_sources_last_fetched_at", "sources", ["last_fetched_at"])

    op.create_table(
        "categories",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("color", sa.String(9), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_categories_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["categories.id"], name="fk_categories_parent_id_categories", ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "user_id", "parent_id", "slug", name="uq_categories_user_parent_slug"
        ),
    )
    op.create_index(
        "ix_categories_user_id_parent_id_position",
        "categories",
        ["user_id", "parent_id", "position"],
    )

    op.create_table(
        "user_sources",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("custom_title", sa.Text(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_sources_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name="fk_user_sources_source_id_sources", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_user_sources_category_id_categories",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "source_id", name="uq_user_sources_user_source"),
    )
    op.create_index(
        "ix_user_sources_user_category", "user_sources", ["user_id", "category_id"]
    )

    op.create_table(
        "featured_sources",
        sa.Column("source_id", sa.BigInteger(), primary_key=True),
        sa.Column("category_hint", sa.String(64), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("featured_until", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_featured_sources_source_id_sources",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_featured_sources_category_hint_position",
        "featured_sources",
        ["category_hint", "position"],
    )


def downgrade() -> None:
    op.drop_index("ix_featured_sources_category_hint_position", table_name="featured_sources")
    op.drop_table("featured_sources")
    op.drop_index("ix_user_sources_user_category", table_name="user_sources")
    op.drop_table("user_sources")
    op.drop_index("ix_categories_user_id_parent_id_position", table_name="categories")
    op.drop_table("categories")
    op.drop_index("ix_sources_last_fetched_at", table_name="sources")
    op.drop_index("ix_sources_status", table_name="sources")
    op.drop_table("sources")
