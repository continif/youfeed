"""Modelli alert + alert_matches (Phase 1.2.D)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .knowledge import Topic


class Alert(Base):
    """Alert dell'utente su un topic.

    Quando un nuovo articolo viene indicizzato e contiene il topic indicato,
    il matcher crea un `AlertMatch` + una `Notification` in-app (e in futuro
    un push se 'push' è in `channels`).
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    channels: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{inapp}"
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    topic: Mapped[Topic] = relationship()

    __table_args__ = (
        UniqueConstraint("user_id", "topic_id", name="uq_alerts_user_topic"),
        Index(
            "ix_alerts_topic_enabled",
            "topic_id",
            postgresql_where="is_enabled IS TRUE",
        ),
    )


class AlertMatch(Base):
    """Match di un alert su un articolo. Composite PK alert_id+article_id
    garantisce l'idempotenza (no duplicate notifications per stesso articolo)."""

    __tablename__ = "alert_matches"

    alert_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True
    )
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    matched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_alert_matches_article", "article_id"),)
