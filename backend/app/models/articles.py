"""Modello Article (metadata in PG, contenuto in Manticore)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .sources import Source


class Article(Base):
    """Metadata articolo. Title/description/content vivono in Manticore (`articles_rt`)."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    url_canonical: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # immagini (vedi DATABASE.md → image storage)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # 'pending' | 'processed' | 'failed' | 'skipped'
    image_processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    processing_status: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    # 'new' | 'extracted' | 'indexed' | 'failed'
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    origin_taxonomy: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    internal_links: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    # aggregati engagement (popolati dal worker activity_log)
    read_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    raw_meta_lite: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    source: Mapped[Source] = relationship()

    __table_args__ = (
        Index("ix_articles_source_published", "source_id", "published_at"),
        Index("ix_articles_published_at", "published_at"),
        Index(
            "ix_articles_processing_status_pending",
            "processing_status",
            postgresql_where="processing_status <> 'indexed'",
        ),
        Index(
            "ix_articles_image_status_pending",
            "image_status",
            postgresql_where="image_status = 'pending'",
        ),
    )
