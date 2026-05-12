"""Endpoint Topic singolo — usato dal frontend per il box info del filtro.

GET /yf_topics/{id} ritorna `display_name`, `description` (da Wikidata) e
`wikipedia_url` (it preferred, fallback en) — informazioni che alimentano
il pannello "su questo topic" mostrato accanto alla timeline quando l'utente
filtra per topic.
"""

from __future__ import annotations

from fastapi import APIRouter, Path
from pydantic import BaseModel, ConfigDict

from app.deps import DB
from app.exceptions import NotFoundError
from app.models import Topic


router = APIRouter(prefix="/yf_topics", tags=["topics"])


class QidRef(BaseModel):
    """Riferimento a un'altra entità Wikidata (Q-id + label umana)."""

    qid: str
    label: str | None = None


class TopicDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    display_name: str
    type: str
    description: str | None = None
    # Campi derivati da topics.external_refs (popolato dall'enrichment
    # Wikidata, Phase 1.2.B).
    wikipedia_url: str | None = None
    wikidata_qid: str | None = None
    instance_of: list[QidRef] = []
    country: list[QidRef] = []
    owned_by: list[QidRef] = []
    official_url: str | None = None


def _qid_refs(raw: object) -> list[QidRef]:
    """Adatta `external_refs.X` (list[dict]) a list[QidRef]. Tollera shape
    legacy (manca `label`) o valori vuoti."""
    if not isinstance(raw, list):
        return []
    out: list[QidRef] = []
    for item in raw:
        if isinstance(item, dict) and item.get("qid"):
            out.append(QidRef(qid=str(item["qid"]), label=item.get("label")))
    return out


@router.get("/{topic_id}", response_model=TopicDetailOut)
async def get_topic(db: DB, topic_id: int = Path(ge=1)) -> TopicDetailOut:
    topic = await db.get(Topic, topic_id)
    if topic is None:
        raise NotFoundError("Topic non trovato.", code="topic_not_found")
    refs = topic.external_refs or {}
    wp_url = refs.get("wikipedia_url_it") or refs.get("wikipedia_url_en")
    return TopicDetailOut(
        id=int(topic.id),
        slug=topic.slug,
        display_name=topic.display_name,
        type=topic.type,
        description=topic.description,
        wikipedia_url=wp_url,
        wikidata_qid=refs.get("wikidata_qid"),
        instance_of=_qid_refs(refs.get("instance_of")),
        country=_qid_refs(refs.get("country")),
        owned_by=_qid_refs(refs.get("owned_by")),
        official_url=refs.get("official_url"),
    )
