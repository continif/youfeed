"""Modelli alert + alert_topics + alert_matches (Phase 1.2.D + ext multi-topic)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .knowledge import Topic


class Alert(Base):
    """Alert dell'utente.

    L'alert ha N topic in `alert_topics`; `match_mode` decide se l'articolo
    deve contenere TUTTI i topic (`'all'`, AND) o ALMENO UNO (`'any'`, OR).
    Default `'all'` per coerenza con la richiesta "alert su 2-3 topic insieme".

    Quando un nuovo articolo viene indicizzato e soddisfa la condizione
    dell'alert, il matcher crea un `AlertMatch` + una `Notification` in-app
    (e un push se 'push' è in `channels`).
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    channels: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{inapp}"
    )
    match_mode: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="all"
    )  # 'all' (AND) | 'any' (OR)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Topic agganciati tramite secondary M:N
    topics: Mapped[list[Topic]] = relationship(
        "Topic",
        secondary="alert_topics",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint("match_mode IN ('all', 'any')", name="ck_alerts_match_mode"),
        Index("ix_alerts_user_id", "user_id"),
    )


class AlertTopic(Base):
    """Join M:N alert ↔ topic. PK composta (no duplicati per alert)."""

    __tablename__ = "alert_topics"

    alert_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_alert_topics_topic_id", "topic_id"),)


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
