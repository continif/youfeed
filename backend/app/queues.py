"""RQ queues — singleton di `Queue` per ogni nome di coda usato da YOUFEED.

Usa la libreria `rq` sync (non async-native). Le chiamate a `queue.enqueue(...)`
sono rapide e bloccanti solo per un round-trip Redis: si possono fare anche
da handler FastAPI async senza problemi.

I worker girano come processi separati (vedi `infra/systemd/yf-worker@.service`).
Esempio per la coda email:

    rq worker --url $RQ_REDIS_URL email
"""

from __future__ import annotations

from functools import lru_cache

from redis import Redis as SyncRedis
from rq import Queue

from app.config import get_settings


# ---------------------------------------------------------------------------
# Nomi delle code (allineati con STATUS.md → infra/systemd/README.md)
# ---------------------------------------------------------------------------

QUEUE_EMAIL = "email"
QUEUE_DISCOVER = "discover"
QUEUE_FETCH_RSS = "fetch_rss"
QUEUE_FETCH_WP = "fetch_wp"
QUEUE_PROCESS_ARTICLE = "process_article"
QUEUE_IMAGE_PROCESSOR = "image_processor"
QUEUE_ACTIVITY_LOG = "activity_log"
QUEUE_MANAGE_PARTITIONS = "manage_partitions"
# v1.2+:
QUEUE_PUSH = "push"
QUEUE_ALERTS_MATCH = "alerts_match"
QUEUE_ENRICH_WIKIDATA = "enrich_wikidata"
QUEUE_RETENTION_SWEEP = "retention_sweep"


@lru_cache(maxsize=1)
def get_rq_redis() -> SyncRedis:
    """Connessione Redis sync per RQ."""
    settings = get_settings()
    return SyncRedis.from_url(settings.rq_redis_url)


@lru_cache(maxsize=None)
def get_queue(name: str) -> Queue:
    """Singleton di Queue per nome. Cached con `lru_cache`."""
    return Queue(name=name, connection=get_rq_redis())
