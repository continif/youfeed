"""Backfill di `sources.lang` per le fonti già presenti.

Per ogni source senza lingua rileva la lingua dai titoli degli articoli
salvati. Per le fonti NON italiane rimuove le righe `article_topics` dei loro
articoli (restano visibili a chi ha la fonte, ma fuori dall'engine).

I topic auto creati in passato da quegli articoli e ormai orfani si vedono
(e si invalidano) da `/yf_admin/topics`. Per allineare anche i campi topic su
Manticore: `python -m app.utils.reindex`.

    python -m app.utils.backfill_source_lang            # dry-run
    python -m app.utils.backfill_source_lang --apply
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import delete, select

from app.db import dispose_engine, get_session_factory
from app.ingestion.lang import detect_language, is_engine_language
from app.models import Article, ArticleTopic, Source

SAMPLE_ARTICLES = 60


async def _main_async(apply: bool) -> None:
    factory = get_session_factory()
    async with factory() as session:
        sources = (
            await session.execute(select(Source).where(Source.lang.is_(None)))
        ).scalars().all()
        for src in sources:
            rows = (
                await session.execute(
                    select(Article.raw_meta_lite)
                    .where(Article.source_id == src.id)
                    .order_by(Article.published_at.desc())
                    .limit(SAMPLE_ARTICLES)
                )
            ).all()
            texts = [
                f"{(r[0] or {}).get('title') or ''} {((r[0] or {}).get('description') or '')[:200]}"
                for r in rows
            ]
            lang = detect_language(texts)
            if lang is None:
                continue
            purged = 0
            if not is_engine_language(lang):
                print(f"source {src.id} [{lang}] {src.title!r} ({src.url_feed or src.wp_api_root})")
                if apply:
                    res = await session.execute(
                        delete(ArticleTopic).where(
                            ArticleTopic.article_id.in_(
                                select(Article.id).where(Article.source_id == src.id)
                            )
                        )
                    )
                    purged = res.rowcount or 0
                    print(f"   article_topics rimossi: {purged}")
            if apply:
                src.lang = lang
        if apply:
            await session.commit()
        else:
            print("(dry-run: nessuna scrittura, usa --apply)")
    await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill sources.lang")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(_main_async(args.apply))


if __name__ == "__main__":
    main()
