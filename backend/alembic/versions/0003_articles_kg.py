"""articles, topics, entities, article_topics, article_entities

Revision ID: 0003_articles_kg
Revises: 0002_sources_categories
Create Date: 2026-05-05

"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_articles_kg"
down_revision: str | Sequence[str] | None = "0002_sources_categories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "articles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("url_canonical", sa.Text(), nullable=False),
        sa.Column("url_hash", sa.String(64), nullable=False),
        # immagini
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("image_local_path", sa.Text(), nullable=True),
        sa.Column("image_width", sa.Integer(), nullable=True),
        sa.Column("image_height", sa.Integer(), nullable=True),
        sa.Column("image_status", sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("image_processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processing_status", sa.String(16), nullable=False, server_default=sa.text("'new'")),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("origin_taxonomy", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("internal_links", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("read_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("open_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_meta_lite", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint("url_hash", name="uq_articles_url_hash"),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name="fk_articles_source_id_sources", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "image_status IN ('pending', 'processed', 'failed', 'skipped')",
            name="ck_articles_image_status",
        ),
        sa.CheckConstraint(
            "processing_status IN ('new', 'extracted', 'indexed', 'failed')",
            name="ck_articles_processing_status",
        ),
    )
    op.create_index(
        "ix_articles_source_published", "articles", ["source_id", "published_at"]
    )
    op.create_index("ix_articles_published_at", "articles", ["published_at"])
    op.create_index(
        "ix_articles_processing_status_pending",
        "articles",
        ["processing_status"],
        postgresql_where=sa.text("processing_status <> 'indexed'"),
    )
    op.create_index(
        "ix_articles_image_status_pending",
        "articles",
        ["image_status"],
        postgresql_where=sa.text("image_status = 'pending'"),
    )

    op.create_table(
        "topics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("external_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_curated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("slug", name="uq_topics_slug"),
        sa.CheckConstraint("type IN ('brand', 'person', 'subject')", name="ck_topics_type"),
    )

    op.create_table(
        "entities",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("surface_form", sa.Text(), nullable=False),
        sa.Column("normalized", sa.Text(), nullable=False),
        sa.Column("ner_type", sa.String(16), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ignored", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("normalized", "ner_type", name="uq_entities_normalized_ner_type"),
        sa.ForeignKeyConstraint(
            ["topic_id"], ["topics.id"], name="fk_entities_topic_id_topics", ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_entities_unresolved_by_count",
        "entities",
        ["occurrence_count"],
        postgresql_where=sa.text("topic_id IS NULL AND ignored = false"),
    )

    op.create_table(
        "article_topics",
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("position", sa.String(16), nullable=False, server_default=sa.text("'body'")),
        sa.PrimaryKeyConstraint("article_id", "topic_id", name="pk_article_topics"),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            name="fk_article_topics_article_id_articles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"], ["topics.id"], name="fk_article_topics_topic_id_topics", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "source IN ('dict', 'ner', 'regex', 'taxonomy', 'llm')",
            name="ck_article_topics_source",
        ),
    )
    op.create_index("ix_article_topics_topic_article", "article_topics", ["topic_id", "article_id"])

    op.create_table(
        "article_entities",
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("in_title", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("article_id", "entity_id", name="pk_article_entities"),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            name="fk_article_entities_article_id_articles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name="fk_article_entities_entity_id_entities",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_article_entities_entity", "article_entities", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_article_entities_entity", table_name="article_entities")
    op.drop_table("article_entities")
    op.drop_index("ix_article_topics_topic_article", table_name="article_topics")
    op.drop_table("article_topics")
    op.drop_index("ix_entities_unresolved_by_count", table_name="entities")
    op.drop_table("entities")
    op.drop_table("topics")
    op.drop_index("ix_articles_image_status_pending", table_name="articles")
    op.drop_index("ix_articles_processing_status_pending", table_name="articles")
    op.drop_index("ix_articles_published_at", table_name="articles")
    op.drop_index("ix_articles_source_published", table_name="articles")
    op.drop_table("articles")
