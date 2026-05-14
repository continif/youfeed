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


class BlockedIp(Base):
    """IP bloccato. `expires_at` nullable: permanente se NULL, temporaneo
    (auto-ban da scanner-path) se valorizzato. Le righe scadute restano in
    tabella e vengono filtrate dalla cache + ripulite da retention_sweep.
    """

    __tablename__ = "blocked_ips"

    ip: Mapped[str] = mapped_column(Text, primary_key=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BlockedUserAgent(Base):
    """Pattern substring (case-insensitive) da matchare contro User-Agent.
    Niente regex per evitare ReDoS: `pattern.lower() in ua.lower()`."""

    __tablename__ = "blocked_user_agents"

    pattern: Mapped[str] = mapped_column(Text, primary_key=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
