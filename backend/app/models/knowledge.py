"""Modelli knowledge graph: topics, entities, article_topics, article_entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    Float,
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

from .articles import Article
from .base import Base


class Topic(Base):
    """Entità canonica curata (brand | person | subject)."""

    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    aliases: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_refs: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_curated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    article_topics: Mapped[list[ArticleTopic]] = relationship(back_populates="topic")
    entities: Mapped[list[Entity]] = relationship(back_populates="topic")


class Entity(Base):
    """Entità raw da NER/regexp; può essere risolta a `Topic` o restare grezza."""

    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    surface_form: Mapped[str] = mapped_column(Text, nullable=False)
    normalized: Mapped[str] = mapped_column(Text, nullable=False)
    ner_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # 'PER' | 'ORG' | 'LOC' | 'MISC' | 'REGEX_PER' | 'REGEX_BRAND'
    topic_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="SET NULL"), nullable=True
    )
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ignored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    topic: Mapped[Topic | None] = relationship(back_populates="entities")

    __table_args__ = (
        UniqueConstraint("normalized", "ner_type", name="uq_entities_normalized_ner_type"),
        Index(
            "ix_entities_unresolved_by_count",
            "occurrence_count",
            postgresql_where="topic_id IS NULL AND ignored = false",
        ),
    )


class ArticleTopic(Base):
    """Arco articolo→topic. M:N con score e source di estrazione."""

    __tablename__ = "article_topics"

    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    # 'dict' | 'ner' | 'regex' | 'taxonomy' | 'llm'
    position: Mapped[str] = mapped_column(String(16), nullable=False, default="body")
    # 'title' | 'body' | 'both'

    article: Mapped[Article] = relationship()
    topic: Mapped[Topic] = relationship(back_populates="article_topics")

    __table_args__ = (Index("ix_article_topics_topic_article", "topic_id", "article_id"),)


class ArticleEntity(Base):
    """Arco articolo→entità raw. Permette tracciamento entità non risolte."""

    __tablename__ = "article_entities"

    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    in_title: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    article: Mapped[Article] = relationship()
    entity: Mapped[Entity] = relationship()

    __table_args__ = (Index("ix_article_entities_entity", "entity_id"),)
