"""SQLite event store per i 403 generati da TrafficBlockMiddleware.

Append-only, WAL mode, scritture via `asyncio.to_thread` (lo stdlib `sqlite3`
è sync; lo wrappiamo invece di aggiungere `aiosqlite` come dipendenza).

Schema:
  block_events(id, ts, ip, country, asn, method, path, user_agent, reason)

Vedi `.claude/SECURITY.md` per il razionale (perché SQLite, retention, query
tipiche).
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS block_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    ip TEXT,
    country TEXT,
    asn INTEGER,
    method TEXT,
    path TEXT,
    user_agent TEXT,
    reason TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_block_events_ts ON block_events(ts DESC);
CREATE INDEX IF NOT EXISTS ix_block_events_country_ts ON block_events(country, ts DESC);
CREATE INDEX IF NOT EXISTS ix_block_events_asn_ts ON block_events(asn, ts DESC);
CREATE INDEX IF NOT EXISTS ix_block_events_ip_ts ON block_events(ip, ts DESC);
"""


_db_path: Path | None = None


def init_store(db_path: Path) -> None:
    """Crea il file SQLite e applica lo schema. Idempotente.

    Chiamato all'avvio dell'app (lifespan). Imposta il path globale così le
    successive `record_block` non devono ripassarlo.
    """
    global _db_path
    _db_path = db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
    log.info("yf.security.events_store_ready", path=str(db_path))


def _insert_sync(
    db_path: Path,
    *,
    ts: int,
    ip: str | None,
    country: str | None,
    asn: int | None,
    method: str | None,
    path: str | None,
    user_agent: str | None,
    reason: str,
) -> None:
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    try:
        conn.execute(
            "INSERT INTO block_events (ts, ip, country, asn, method, path, user_agent, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, ip, country, asn, method, path, user_agent, reason),
        )
        conn.commit()
    finally:
        conn.close()


async def record_block(
    *,
    ip: str | None,
    country: str | None,
    asn: int | None,
    method: str | None,
    path: str | None,
    user_agent: str | None,
    reason: str,
) -> None:
    """Registra un 403. Non solleva: se la scrittura fallisce, logga e basta
    (il blocco è già stato applicato, niente da fare lato user)."""
    if _db_path is None:
        return
    try:
        await asyncio.to_thread(
            _insert_sync,
            _db_path,
            ts=int(time.time()),
            ip=ip,
            country=country,
            asn=asn,
            method=method,
            path=path,
            user_agent=(user_agent or "")[:500] or None,
            reason=reason,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("yf.security.record_block_failed", error=str(e))


def _query_sync(
    db_path: Path,
    sql: str,
    params: tuple[Any, ...],
) -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return list(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


async def list_events(
    *,
    country: str | None = None,
    asn: int | None = None,
    ip: str | None = None,
    reason: str | None = None,
    since_ts: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Lista eventi recenti con filtri opzionali. Default ordina ts DESC."""
    if _db_path is None:
        return []
    where: list[str] = []
    params: list[Any] = []
    if country:
        where.append("country = ?")
        params.append(country)
    if asn is not None:
        where.append("asn = ?")
        params.append(asn)
    if ip:
        where.append("ip = ?")
        params.append(ip)
    if reason:
        where.append("reason = ?")
        params.append(reason)
    if since_ts is not None:
        where.append("ts >= ?")
        params.append(since_ts)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    sql = (
        "SELECT id, ts, ip, country, asn, method, path, user_agent, reason "
        f"FROM block_events{clause} ORDER BY ts DESC LIMIT ?"
    )
    params.append(int(limit))
    rows = await asyncio.to_thread(_query_sync, _db_path, sql, tuple(params))
    return [dict(r) for r in rows]


async def aggregate(
    *,
    group_by: str,
    since_ts: int,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Top-N per `group_by` (uno fra: country, asn, ip, path) dall'`since_ts`.

    Ritorna [{value, count}, …] ordinato per count desc.
    """
    if group_by not in ("country", "asn", "ip", "path"):
        raise ValueError(f"group_by non valido: {group_by!r}")
    if _db_path is None:
        return []
    sql = (
        f"SELECT {group_by} AS value, COUNT(*) AS count "
        "FROM block_events WHERE ts >= ? "
        f"GROUP BY {group_by} ORDER BY count DESC LIMIT ?"
    )
    rows = await asyncio.to_thread(_query_sync, _db_path, sql, (since_ts, int(limit)))
    return [dict(r) for r in rows]


async def total_count(since_ts: int) -> int:
    if _db_path is None:
        return 0
    rows = await asyncio.to_thread(
        _query_sync,
        _db_path,
        "SELECT COUNT(*) AS n FROM block_events WHERE ts >= ?",
        (since_ts,),
    )
    return int(rows[0]["n"]) if rows else 0


def prune_older_than(days: int) -> int:
    """Cancella eventi più vecchi di `days` giorni. Ritorna il numero di righe
    cancellate. Sync — chiamare da utility/CLI o cron, non dal request path."""
    if _db_path is None:
        return 0
    cutoff = int(time.time()) - days * 86400
    conn = sqlite3.connect(str(_db_path))
    try:
        cur = conn.execute("DELETE FROM block_events WHERE ts < ?", (cutoff,))
        n = cur.rowcount or 0
        conn.commit()
    finally:
        conn.close()
    return n
