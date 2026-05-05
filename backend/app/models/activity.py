"""Modello ActivityLog (partitioned by ts daily).

NB: la PARTITION BY RANGE è applicata nella migration via raw SQL — Alembic
autogenerate non gestisce nativamente le partition table. Qui SQLAlchemy
"vede" la tabella come ordinaria; le query funzionano regolarmente perché
PG fa partition pruning automatico.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Integer, PrimaryKeyConstraint, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ActivityLog(Base):
    """Log eventi (partitioned daily). Vedi DATABASE.md → activity_log."""

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(BigInteger, autoincrement=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)

    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # 'http_request' | 'impression' | 'click' | 'dwell' | 'scroll' | 'search' | ...
    route: Mapped[str | None] = mapped_column(Text, nullable=True)
    method: Mapped[str | None] = mapped_column(String(8), nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    asn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ua: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("id", "ts", name="pk_activity_log"),
        Index("ix_activity_log_user_ts", "user_id", "ts"),
        Index("ix_activity_log_target", "target_type", "target_id"),
        # NB: postgresql_partition_by viene applicato manualmente nella migration
        {"postgresql_partition_by": "RANGE (ts)"},
    )
