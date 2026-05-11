"""Worker RQ: scarica + processa l'immagine di un articolo.

Pattern come `workers/email.py` e `workers/fetch.py`: funzione top-level
sync che chiama `asyncio.run(...)` per il core async.

Stato dell'articolo (`articles.image_status`):
- 'pending'   : da processare
- 'processed' : varianti WebP salvate, image_local_path popolato
- 'failed'    : decode/download fallito (non ritento, motivo loggato)
- 'skipped'   : nessun image_url disponibile (decisione presa in fetch)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from app.db import get_session_factory
from app.ingestion import image_processor
from app.models import Article
from app.queues import QUEUE_IMAGE_PROCESSOR, get_queue

log = structlog.get_logger()


async def _process_async(article_id: int) -> None:
    factory = get_session_factory()
    async with factory() as session:
        article = await session.get(Article, article_id)
        if article is None:
            log.warning("yf.image.article_missing", article_id=article_id)
            return
        if not article.image_url:
            article.image_status = "skipped"
            article.image_processed_at = datetime.now(UTC)
            await session.commit()
            return

        result = await image_processor.process_image(article.image_url)
        if result is None:
            article.image_status = "failed"
            article.image_processed_at = datetime.now(UTC)
            await session.commit()
            log.info("yf.image.failed", article_id=article_id, url=article.image_url)
            return

        article.image_local_path = result.relative_path
        article.image_width = result.width
        article.image_height = result.height
        article.image_status = "processed"
        article.image_processed_at = datetime.now(UTC)
        await session.commit()
        log.info(
            "yf.image.processed",
            article_id=article_id,
            path=result.relative_path,
            w=result.width,
            h=result.height,
        )


def process_image_job(*, article_id: int) -> None:
    try:
        asyncio.run(_process_async(article_id))
    except Exception as e:
        log.error("yf.image.job_failed", article_id=article_id, error=str(e))
        raise


def enqueue_image(article_id: int) -> None:
    queue = get_queue(QUEUE_IMAGE_PROCESSOR)
    queue.enqueue(process_image_job, article_id=article_id, job_timeout="2m")
