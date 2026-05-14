"""Modelli per il blocco del traffico (config admin)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CHAR, BigInteger, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class BlockedCountry(Base):
    """Country bloccato: tutte le richieste con `request.state.country == iso_code`
    ricevono 403 dal TrafficBlockMiddleware."""

    __tablename__ = "blocked_countries"

    iso_code: Mapped[str] = mapped_column(CHAR(2), primary_key=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BlockedAsn(Base):
    """ASN bloccato: tutte le richieste con `request.state.asn == asn`
    ricevono 403 dal TrafficBlockMiddleware."""

    __tablename__ = "blocked_asns"

    asn: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
