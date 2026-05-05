"""Modelli sources, categorie, user_sources, featured_sources."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .users import User

# enum-like: kind ∈ {'rss', 'wordpress_api', 'invalid'}
# enum-like: status ∈ {'pending', 'active', 'broken', 'paused'}


class Source(Base, TimestampMixin):
    """Fonte normalizzata, condivisa tra utenti."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    url_site: Mapped[str | None] = mapped_column(Text, nullable=True)
    url_feed: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    wp_api_root: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    favicon_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    poll_interval: Mapped[int] = mapped_column(Integer, nullable=False, default=1800)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    etag: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_modified: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discovery_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    user_sources: Mapped[list[UserSource]] = relationship(back_populates="source")

    __table_args__ = (
        Index("ix_sources_status", "status"),
        Index("ix_sources_last_fetched_at", "last_fetched_at"),
    )


class Category(Base):
    """Alberatura categorie per utente (parent_id ricorsivo)."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categories.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    color: Mapped[str | None] = mapped_column(String(9), nullable=True)  # "#rrggbb" o "#rrggbbaa"
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="categories")
    parent: Mapped[Category | None] = relationship(remote_side="Category.id", backref="children")
    user_sources: Mapped[list[UserSource]] = relationship(back_populates="category")

    __table_args__ = (
        UniqueConstraint("user_id", "parent_id", "slug", name="uq_categories_user_parent_slug"),
        Index("ix_categories_user_id_parent_id_position", "user_id", "parent_id", "position"),
    )


class UserSource(Base):
    """Relazione utente↔fonte, 1:N con categoria (categoria_id obbligatoria)."""

    __tablename__ = "user_sources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    custom_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="user_sources")
    source: Mapped[Source] = relationship(back_populates="user_sources")
    category: Mapped[Category] = relationship(back_populates="user_sources")

    __table_args__ = (
        UniqueConstraint("user_id", "source_id", name="uq_user_sources_user_source"),
        Index("ix_user_sources_user_category", "user_id", "category_id"),
    )


class FeaturedSource(Base):
    """Fonti popolari pre-curate, mostrate in `<FeaturedSourcesGallery>`."""

    __tablename__ = "featured_sources"

    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    category_hint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    featured_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source: Mapped[Source] = relationship()

    __table_args__ = (Index("ix_featured_sources_category_hint_position", "category_hint", "position"),)


# Per Alembic autogenerate: import esplicito sotto a evitare cicli
_ = ARRAY  # noqa: F841 — riservato per futuri ARRAY[Text] su origin_taxonomy
