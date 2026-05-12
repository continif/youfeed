"""Modello bookmark (saved articles)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, PrimaryKeyConstraint, func
from sqlalchemy.orm import Mapped, mapped_column


from .base import Base


class ArticleBookmark(Base):
    """Un articolo salvato (bookmark) da un utente.

    PK composita (user_id, article_id) impedisce duplicati. Entrambe le FK
    cascadano su delete: niente bookmark orfani se l'utente o l'articolo
    vengono rimossi.
    """

    __tablename__ = "article_bookmarks"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "article_id", name="pk_article_bookmarks"),
        Index(
            "ix_article_bookmarks_user_created",
            "user_id",
            "created_at",
            postgresql_using="btree",
        ),
    )
