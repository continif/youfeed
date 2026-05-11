"""CLI utility per re-indicizzare articoli già processati.

Use case: dopo un fix in `ingestion/normalize.py` (es. strip script/style,
double-encoded tags), il content_text salvato in Manticore è "vecchio".
Questo comando ri-esegue `process_article_job` per gli id specificati.

Esempi:
    # Re-indicizza tutti gli articoli con processing_status='indexed'
    python -m app.utils.reindex --all

    # Solo gli articoli appartenenti a una source
    python -m app.utils.reindex --source-id 3

    # Solo quelli con HTML grezzo che contiene script/style
    python -m app.utils.reindex --suspicious
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog
from sqlalchemy import select, text

from app.db import dispose_engine, get_session_factory
from app.models import Article
from app.workers.process import _process_async

log = structlog.get_logger()


async def _select_ids(
    *, all_indexed: bool, source_id: int | None, suspicious: bool
) -> list[int]:
    factory = get_session_factory()
    async with factory() as session:
        if suspicious:
            res = await session.execute(
                text(
                    """
                    SELECT id FROM articles
                    WHERE processing_status = 'indexed'
                      AND (
                        raw_meta_lite::text ILIKE '%<style%' OR
                        raw_meta_lite::text ILIKE '%<script%' OR
                        raw_meta_lite::text ILIKE '%<noscript%' OR
                        raw_meta_lite::text ILIKE '%&lt;strong&gt;%' OR
                        raw_meta_lite::text ILIKE '%&lt;b&gt;%' OR
                        raw_meta_lite::text ILIKE '%&lt;em&gt;%' OR
                        raw_meta_lite::text ILIKE '%&lt;p&gt;%'
                      )
                    ORDER BY id
                    """
                )
            )
            return [int(r[0]) for r in res.all()]

        stmt = select(Article.id).where(Article.processing_status == "indexed")
        if source_id is not None:
            stmt = stmt.where(Article.source_id == source_id)
        if not all_indexed and source_id is None:
            return []
        stmt = stmt.order_by(Article.id)
        res = await session.execute(stmt)
        return [int(r[0]) for r in res.all()]


async def _main_async(args: argparse.Namespace) -> None:
    ids = await _select_ids(
        all_indexed=args.all,
        source_id=args.source_id,
        suspicious=args.suspicious,
    )
    print(f"-> {len(ids)} articoli da re-indicizzare", flush=True)

    ok = 0
    failed = 0
    for i, aid in enumerate(ids, start=1):
        try:
            await _process_async(aid)
            ok += 1
        except Exception as e:
            failed += 1
            log.warning("yf.reindex.failed", article_id=aid, error=str(e))
        if i % 50 == 0:
            print(f"   {i}/{len(ids)}  ok={ok}  fail={failed}", flush=True)
    print(f"== fine: ok={ok}  fail={failed}", flush=True)
    await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-indicizza articoli su Manticore")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="Tutti gli articoli indexed")
    g.add_argument("--source-id", type=int, help="Solo una source")
    g.add_argument(
        "--suspicious",
        action="store_true",
        help="Solo articoli con HTML grezzo che ha script/style/tag-encoded",
    )
    args = parser.parse_args()
    try:
        asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
