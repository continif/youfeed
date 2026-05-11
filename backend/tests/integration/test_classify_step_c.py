"""Integration test per Step C del classify (regex extractor live, T-012).

Verifica che il pipeline classify, dopo il dict match, esegua REGEX_PER e
REGEX_MODEL e crei `Topic(is_curated=false)` con `ArticleTopic(source='regex')`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.ingestion import classify
from app.models import Topic
from app.services import ingestion_service

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _invalidate_cache_per_test():
    classify.invalidate_classifier_cache()
    yield
    classify.invalidate_classifier_cache()


async def _add_curated_brand(db_session, slug: str, display_name: str) -> Topic:
    """Helper: crea un brand curated nel DB. Necessario per abilitare REGEX_MODEL
    (la whitelist brand viene derivata dai brand curated già matched dal dict)."""
    t = Topic(
        type="brand",
        slug=slug,
        display_name=display_name,
        aliases=[],
        is_curated=True,
    )
    db_session.add(t)
    await db_session.flush()
    return t


async def test_step_c_extracts_person_not_in_curated(db_session) -> None:
    """T-012: una persona non-curated tipo 'Mario Rossi' deve essere estratta
    via REGEX_PER e creare un Topic(type='person', is_curated=false)."""
    matches = await classify.classify(
        db_session,
        title="Mario Rossi annuncia il nuovo progetto",
        body_text="Il consulente Mario Rossi ha lavorato a Roma.",
    )
    await db_session.commit()

    person_matches = [m for m in matches if m.source == "regex"]
    assert person_matches, "Nessun match regex trovato"
    # Trova il topic creato
    rossi = (
        await db_session.execute(select(Topic).where(Topic.slug == "mario-rossi"))
    ).scalar_one()
    assert rossi.type == "person"
    assert rossi.is_curated is False
    assert rossi.display_name == "Mario Rossi"
    # Lo score del match deve corrispondere
    rossi_match = next(m for m in person_matches if m.topic_id == int(rossi.id))
    assert rossi_match.in_title is True
    assert rossi_match.in_body is True


async def test_step_c_extracts_model_when_brand_is_matched(db_session) -> None:
    """REGEX_MODEL gira solo se almeno un brand curated è stato matched dal
    dict (perché serve la whitelist). 'Apple iPhone 15 Pro' → topic 'model'."""
    await _add_curated_brand(db_session, "apple", "Apple")
    await db_session.commit()

    matches = await classify.classify(
        db_session,
        title="Apple presenta il nuovo iPhone",
        body_text="Il nuovo Apple iPhone 15 Pro è in vendita ora.",
    )
    await db_session.commit()

    regex_matches = [m for m in matches if m.source == "regex"]
    assert regex_matches, "Atteso almeno un match regex"
    types = []
    for m in regex_matches:
        types.append(await _topic_type(db_session, m.topic_id))
    assert "model" in types, f"Atteso almeno un topic type='model', visti: {types}"


async def test_step_c_caps_at_max_persons_per_article(db_session) -> None:
    """Il cap MAX_REGEX_PERSONS_PER_ARTICLE evita esplosioni. 8 persone nel
    title → max 5 entrano nei match per type='person'."""
    title = (
        "Mario Rossi, Luca Bianchi, Giuseppe Verdi, Anna Ferrari, "
        "Francesca Romano, Paolo Conti, Maria Esposito, Giorgia Russo"
    )
    matches = await classify.classify(db_session, title=title, body_text="")
    await db_session.commit()

    # Conta solo i match person (regex extractor estrae anche brand_single
    # nel pipeline live, con cap separato MAX_REGEX_BRANDS_PER_ARTICLE).
    person_topic_types = []
    for m in matches:
        if m.source != "regex":
            continue
        topic_type = await _topic_type(db_session, m.topic_id)
        if topic_type == "person":
            person_topic_types.append(m)
    assert len(person_topic_types) <= classify.MAX_REGEX_PERSONS_PER_ARTICLE


async def test_step_c_disabled_skips_regex(db_session) -> None:
    """Con `enable_regex_extraction=False` (override esplicito), Step C non gira.

    NB: Step D (NER spaCy) è ortogonale a Step C — il test lo disabilita anche
    per isolare il comportamento di Step C.
    """
    matches = await classify.classify(
        db_session,
        title="Mario Rossi annuncia",
        body_text="Mario Rossi parla.",
        enable_regex_extraction=False,
        enable_ner_extraction=False,
    )
    assert all(m.source == "dict" for m in matches)


async def test_step_c_idempotent_on_reclassify(db_session) -> None:
    """Rilanciare classify sullo stesso testo non duplica i topic. L'upsert
    su slug riusa il record esistente."""
    title = "Sandra Mondaini ha presentato lo show ieri sera."
    body = "Sandra Mondaini ha condotto."

    await classify.classify(db_session, title=title, body_text=body)
    await db_session.commit()
    n1 = (
        await db_session.execute(select(Topic).where(Topic.slug == "sandra-mondaini"))
    ).scalars().all()
    assert len(n1) == 1

    # Seconda chiamata
    await classify.classify(db_session, title=title, body_text=body)
    await db_session.commit()
    n2 = (
        await db_session.execute(select(Topic).where(Topic.slug == "sandra-mondaini"))
    ).scalars().all()
    assert len(n2) == 1, "Il topic regex non deve essere duplicato"


async def test_step_c_apply_classification_persists_source_regex(db_session) -> None:
    """Quando i match (source='regex') vengono passati ad apply_classification,
    le righe in article_topics hanno source='regex'."""
    from app.models import Article, ArticleTopic, Source

    src = Source(kind="rss", url_feed="https://x.com/feed.xml", title="X", status="active")
    db_session.add(src)
    await db_session.flush()
    art = Article(
        source_id=src.id,
        kind="rss",
        url_canonical="https://x.com/a1",
        url_hash="h-stepC",
        published_at=datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC),
        processing_status="indexed",
        raw_meta_lite={"title": "Daniele Capezzone parla di politica"},
    )
    db_session.add(art)
    await db_session.flush()

    matches = await classify.classify(
        db_session,
        title="Daniele Capezzone parla di politica",
        body_text="",
    )
    await ingestion_service.apply_classification(
        db_session, article_id=int(art.id), matches=matches
    )
    await db_session.commit()

    rows = (
        await db_session.execute(
            select(ArticleTopic).where(ArticleTopic.article_id == art.id)
        )
    ).scalars().all()
    assert any(r.source == "regex" for r in rows), "Almeno una riga con source='regex' attesa"


async def _topic_type(db_session, topic_id: int) -> str:
    """Helper: ritorna il `type` di un Topic dato il suo id."""
    t = (
        await db_session.execute(select(Topic.type).where(Topic.id == topic_id))
    ).scalar_one_or_none()
    return t or ""


async def test_step_c_extracts_brand_single_in_mid_sentence(db_session) -> None:
    """T-014: brand singolo non-curated in mid-sentence (es. 'Brembo' in
    'frenata di Brembo entra in produzione') deve uscire come Topic
    (type='brand', is_curated=false) via REGEX_BRAND_SINGLE."""
    matches = await classify.classify(
        db_session,
        title="La frenata di Brembo entra in produzione",
        body_text="",
    )
    await db_session.commit()

    regex_matches = [m for m in matches if m.source == "regex"]
    assert regex_matches, "Atteso almeno un match regex"
    types_and_ids: list[tuple[str, int]] = []
    for m in regex_matches:
        types_and_ids.append((await _topic_type(db_session, m.topic_id), m.topic_id))
    assert any(t == "brand" for t, _ in types_and_ids), (
        f"Atteso topic type='brand' per Brembo, visti: {types_and_ids}"
    )
    # Verifica che il display_name sia corretto
    brembo = (
        await db_session.execute(select(Topic).where(Topic.slug == "brembo"))
    ).scalar_one_or_none()
    assert brembo is not None
    assert brembo.display_name == "Brembo"


async def test_step_d_ner_extracts_single_token_person(db_session) -> None:
    """Step D NER cattura single-token PER che il regex (≥2 token) non vede.

    "Yoshi conquista i fan" → spaCy → PER 'Yoshi' → topic person is_curated=False.
    """
    matches = await classify.classify(
        db_session,
        title="Yoshi conquista i fan dopo il successo di Super Mario",
        body_text="",
        enable_regex_extraction=False,  # isolo Step D
    )
    await db_session.commit()

    ner_matches = [m for m in matches if m.source == "ner"]
    assert ner_matches, "Atteso almeno un match NER su single-token PER"
    yoshi = (
        await db_session.execute(select(Topic).where(Topic.slug == "yoshi"))
    ).scalar_one_or_none()
    assert yoshi is not None
    assert yoshi.type == "person"
    assert yoshi.is_curated is False


async def test_step_d_ner_disabled_when_flag_off(db_session) -> None:
    """Con `enable_ner_extraction=False` Step D non gira."""
    matches = await classify.classify(
        db_session,
        title="Yoshi conquista i fan",
        body_text="",
        enable_regex_extraction=False,
        enable_ner_extraction=False,
    )
    assert all(m.source != "ner" for m in matches)
