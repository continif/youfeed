"""CLI per ri-classificare i topic degli articoli già indicizzati.

Use case tipico: dopo aver espanso `infra/seed/topics.yaml` o aggiornato la
blacklist/regex dell'extractor, vogliamo che le nuove regole valgano anche
sugli articoli già processati. Questo tool **non** ri-fetcha né tocca
Manticore: si limita a:

  1. invalidare la cache del classifier (forza il reload dei topics curated)
  2. iterare sugli articoli `processing_status='indexed'` (filtrabili)
  3. per ognuno: estrarre titolo + descrizione da `raw_meta_lite`,
     chiamare `classify.classify(...)` e sostituire le righe di
     `article_topics` con `apply_classification(...)`
  4. opzionalmente: scaricare anche `content_text` da Manticore via
     `--include-content` per classify più accurata (ma ~10x più lenta)

Esempi:
    # Tutti gli articoli indexed, solo title+description
    python -m app.utils.reclassify_topics --all

    # Solo una source
    python -m app.utils.reclassify_topics --source-id 3

    # Pieno (Manticore content_text incluso) — più lento, più accurato
    python -m app.utils.reclassify_topics --all --include-content

L'operazione è idempotente (delete+insert su `article_topics` per ogni
articolo). Sicuro da rilanciare.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from typing import Any

import structlog
from selectolax.parser import HTMLParser
from sqlalchemy import select

from app.db import dispose_engine, get_session_factory
from app.ingestion import classify, manticore_client
from app.models import Article
from app.services import ingestion_service

log = structlog.get_logger()


def _html_to_text(html: str) -> str:
    """Strip HTML tags da `content_html` per ricavare testo plain.
    Usato come fallback quando Manticore non restituisce `content_text`.

    Rimuove sezioni di rumore (navigazione, sidebar, footer, header, form,
    script, style) PRIMA di estrarre il testo: senza questa pulizia
    l'estrazione regex raccoglie testo UI tipo "Home Quantum",
    "INVIA Iscriviti" da menu/widget/form newsletter.
    """
    if not html:
        return ""
    try:
        tree = HTMLParser(html)
        for selector in (
            "nav",
            "aside",
            "footer",
            "header",
            "form",
            "script",
            "style",
            "noscript",
        ):
            for node in tree.css(selector):
                node.decompose()
        return (tree.text(separator=" ") or "").strip()
    except Exception:
        return ""


async def _select_articles(
    *, all_indexed: bool, source_id: int | None, limit: int | None
) -> list[Article]:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(Article).where(Article.processing_status == "indexed")
        if source_id is not None:
            stmt = stmt.where(Article.source_id == source_id)
        if not all_indexed and source_id is None:
            return []
        stmt = stmt.order_by(Article.id)
        if limit is not None:
            stmt = stmt.limit(limit)
        res = await session.execute(stmt)
        return list(res.scalars().all())


async def _content_text_map(article_ids: list[int]) -> dict[int, str]:
    """Pull `content_text` da Manticore in batch. Restituisce dict id -> testo
    (vuoto se Manticore non ha il documento)."""
    if not article_ids:
        return {}
    docs = await manticore_client.get_by_ids(article_ids)
    return {aid: (docs.get(aid) or {}).get("content_text") or "" for aid in article_ids}


async def _reclassify_one(
    session_factory: Any,
    article: Article,
    *,
    body_text: str,
    enable_regex_extraction: bool = True,
    enable_ner_extraction: bool = True,
    title_only: bool = False,
) -> int:
    """Classifica un articolo e sostituisce le righe in article_topics.
    Ritorna il numero di topic match scritti.

    Con `enable_regex_extraction=False` salta la fase NER/regex: nessun nuovo
    topic auto-extracted viene creato; restano solo i match contro i topic
    curated già in DB. Utile dopo una passata di moderazione manuale.

    Con `title_only=True` ignora body_text + description + origin_taxonomy:
    estrae solo dal titolo (allineato al worker live, riduce FP da body).
    """
    meta = article.raw_meta_lite or {}
    title = (meta.get("title") or "").strip()
    if title_only:
        body_blob = ""
        origin_taxonomy = None
    else:
        description = (meta.get("description") or "").strip()
        # Body precedence: Manticore content_text (se disponibile) > content_html
        # parsato a testo (fallback locale, indipendente da Manticore).
        if not body_text:
            body_text = _html_to_text(meta.get("content_html") or "")
        body_blob = "\n\n".join(filter(None, [description, body_text]))
        origin_taxonomy = meta.get("origin_taxonomy") or None

    factory = session_factory
    async with factory() as session:
        matches = await classify.classify(
            session,
            title=title,
            body_text=body_blob,
            origin_taxonomy=origin_taxonomy,
            enable_regex_extraction=enable_regex_extraction,
            enable_ner_extraction=enable_ner_extraction,
        )
        n = await ingestion_service.apply_classification(
            session, article_id=int(article.id), matches=matches
        )
        await session.commit()
        return n


async def _main_async(args: argparse.Namespace) -> None:
    # Forza il reload del cache classify: dopo un aggiornamento del seed
    # (`seed_loader --topics ...`) la cache vecchia non riflette i nuovi alias.
    classify.invalidate_classifier_cache()

    articles = await _select_articles(
        all_indexed=args.all,
        source_id=args.source_id,
        limit=args.limit,
    )
    print(f"-> {len(articles)} articoli da ri-classificare", flush=True)
    if not articles:
        await dispose_engine()
        return

    content_map: dict[int, str] = {}
    if args.include_content:
        print("   fetching content_text da Manticore...", flush=True)
        # Chunk per evitare query gigantesche (Manticore via HTTP JSON regge ~500/req).
        chunk = 500
        for i in range(0, len(articles), chunk):
            batch_ids = [int(a.id) for a in articles[i : i + chunk]]
            content_map.update(await _content_text_map(batch_ids))
        print(f"   recuperati {len(content_map)} doc Manticore", flush=True)

    factory = get_session_factory()
    t0 = time.monotonic()
    ok = 0
    failed = 0
    total_matches = 0
    for i, article in enumerate(articles, start=1):
        body = content_map.get(int(article.id), "") if args.include_content else ""
        try:
            n = await _reclassify_one(
                factory, article, body_text=body,
                enable_regex_extraction=not args.curated_only,
                enable_ner_extraction=not args.curated_only and not args.no_ner,
                title_only=args.title_only,
            )
            ok += 1
            total_matches += n
        except Exception as e:
            failed += 1
            log.warning("yf.reclassify.failed", article_id=int(article.id), error=str(e))
        if i % 100 == 0 or i == len(articles):
            elapsed = time.monotonic() - t0
            rate = i / elapsed if elapsed > 0 else 0
            print(
                f"   {i}/{len(articles)}  ok={ok}  fail={failed}  "
                f"topics_inserted={total_matches}  ({rate:.1f}/s)",
                flush=True,
            )
    print(f"== fine: ok={ok}  fail={failed}  topics_inserted_totali={total_matches}", flush=True)
    await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ri-classifica i topic degli articoli già indicizzati"
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="Tutti gli articoli indexed")
    g.add_argument("--source-id", type=int, help="Solo una source")
    parser.add_argument(
        "--limit", type=int, default=None, help="Limite max articoli (debug)"
    )
    parser.add_argument(
        "--include-content",
        action="store_true",
        help="Scarica content_text da Manticore (più lento, più accurato).",
    )
    parser.add_argument(
        "--curated-only",
        action="store_true",
        help=(
            "Disabilita la fase NER/regex (auto-extraction): salva solo i "
            "match contro i topic curated già in DB. Utile dopo una "
            "moderazione manuale per non ricreare topic auto."
        ),
    )
    parser.add_argument(
        "--title-only",
        action="store_true",
        help=(
            "Estrai topic solo dal titolo (ignora body, description, "
            "origin_taxonomy). Allineato col worker live, riduce FP."
        ),
    )
    parser.add_argument(
        "--no-ner",
        action="store_true",
        help=(
            "Disabilita lo Step D NER (spaCy). Utile per A/B test o se "
            "spaCy non è installato. Default: NER attivo."
        ),
    )
    args = parser.parse_args()
    try:
        asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
