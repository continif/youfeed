"""CLI per aggiornare il titolo delle fonti senza nome (o con bot-challenge).

Use case: dopo il fix di `discovery.py` per gestire i siti dietro Cloudflare,
le fonti già salvate con `title=NULL` o `title='Just a moment...'` non si
auto-correggono. Questo tool ri-fetcha il feed RSS / il root `/wp-json/` e
aggiorna `Source.title` (e `Source.favicon_url` se mancante).

Esempi:
    # Solo le fonti con title NULL/vuoto/bot-challenge (default)
    python -m app.utils.refresh_source_titles

    # Forza refresh anche per le fonti con title già valorizzato
    python -m app.utils.refresh_source_titles --all

    # Dry run: mostra cosa cambierebbe senza scrivere
    python -m app.utils.refresh_source_titles --dry-run

L'operazione è idempotente.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx
import structlog
from sqlalchemy import or_, select

from app.db import dispose_engine, get_session_factory
from app.ingestion import discovery
from app.models import Source

log = structlog.get_logger()


def _select_stmt(*, refresh_all: bool):
    stmt = select(Source)
    if not refresh_all:
        # title NULL/empty oppure matcha un bot-challenge marker
        title_lower = Source.title  # type: ignore[assignment]
        like_clauses = [Source.title.ilike(f"%{m}%") for m in discovery.BAD_TITLE_MARKERS]
        stmt = stmt.where(
            or_(
                Source.title.is_(None),
                title_lower == "",
                *like_clauses,
            )
        )
    return stmt.order_by(Source.id)


async def _fetch_rss_title(
    client: httpx.AsyncClient, url_feed: str
) -> str | None:
    resp = await discovery._fetch(client, url_feed)
    if resp is None or resp.status_code != 200:
        return None
    title, _sample = discovery._try_parse_feed(resp.content)
    if title and title.strip():
        return title.strip()
    return None


async def _fetch_wp_title(
    client: httpx.AsyncClient, wp_api_root: str
) -> str | None:
    return await discovery._wp_site_name(client, wp_api_root)


async def _refresh_one(
    client: httpx.AsyncClient, src: Source
) -> str | None:
    """Ritorna il nuovo titolo (o None se non è stato possibile recuperarlo)."""
    if src.kind == "rss" and src.url_feed:
        return await _fetch_rss_title(client, src.url_feed)
    if src.kind == "wordpress_api" and src.wp_api_root:
        return await _fetch_wp_title(client, src.wp_api_root)
    return None


async def main(*, refresh_all: bool, dry_run: bool) -> int:
    factory = get_session_factory()
    async with factory() as session:
        sources = list(
            (await session.execute(_select_stmt(refresh_all=refresh_all)))
            .scalars()
            .all()
        )

    if not sources:
        print("Nessuna fonte da aggiornare.", file=sys.stderr)
        return 0

    print(f"Trovate {len(sources)} fonti da aggiornare.", file=sys.stderr)

    headers = {
        "User-Agent": discovery.USER_AGENT,
        "Accept-Language": "it,en;q=0.5",
    }
    updated = 0
    skipped = 0

    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        for src in sources:
            new_title = await _refresh_one(client, src)
            if not new_title:
                print(
                    f"  [skip] id={src.id} {src.kind}  "
                    f"url={src.url_feed or src.wp_api_root or src.url_site}: "
                    f"impossibile recuperare il titolo",
                    file=sys.stderr,
                )
                skipped += 1
                continue
            old = src.title or "(vuoto)"
            print(f"  [{'DRY' if dry_run else 'OK '}] id={src.id} {src.kind}  {old!r} → {new_title!r}")
            if not dry_run:
                async with factory() as session:
                    obj = await session.get(Source, src.id)
                    if obj is not None:
                        obj.title = new_title
                        await session.commit()
            updated += 1

    print(
        f"\nFatto: {updated} aggiornate, {skipped} non recuperabili.",
        file=sys.stderr,
    )
    await dispose_engine()
    return 0


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--all",
        action="store_true",
        help="Refresh anche le fonti con title già valorizzato.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra cosa cambierebbe senza scrivere su DB.",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(refresh_all=args.all, dry_run=args.dry_run)))


if __name__ == "__main__":
    cli()
