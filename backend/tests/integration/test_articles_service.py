"""Integration test per app.services.articles_service (timeline)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Article, Category, Source, User, UserSource
from app.services import articles_service

pytestmark = pytest.mark.integration


async def _make_user(db_session, *, username: str, verified: bool = True) -> User:
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash="$argon2id$dummy",
        email_verified=verified,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_source(db_session, url: str) -> Source:
    src = Source(kind="rss", url_feed=url, title=f"Source {url}", status="active")
    db_session.add(src)
    await db_session.flush()
    return src


async def _make_category(
    db_session, *, user: User, name: str, public: bool
) -> Category:
    cat = Category(
        user_id=user.id,
        name=name,
        slug=name.lower(),
        is_public=public,
        position=0,
    )
    db_session.add(cat)
    await db_session.flush()
    return cat


async def _link(db_session, *, user: User, source: Source, category: Category) -> None:
    db_session.add(
        UserSource(user_id=user.id, source_id=source.id, category_id=category.id)
    )
    await db_session.flush()


async def _add_article(
    db_session,
    *,
    source: Source,
    title: str,
    minutes_ago: int,
    indexed: bool = True,
) -> Article:
    a = Article(
        source_id=source.id,
        kind="rss",
        url_canonical=f"https://x.com/{title.replace(' ', '-')}",
        url_hash=f"hash-{title}",
        published_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        processing_status="indexed" if indexed else "new",
        raw_meta_lite={"title": title, "description": f"Desc di {title}"},
    )
    db_session.add(a)
    await db_session.flush()
    return a


# ---------------------------------------------------------------------------
# timeline_for_user
# ---------------------------------------------------------------------------


async def test_timeline_for_user_only_includes_subscribed_sources(db_session) -> None:
    user = await _make_user(db_session, username="alice")
    cat = await _make_category(db_session, user=user, name="Cat", public=True)

    src_subscribed = await _make_source(db_session, "https://sub.com/feed.xml")
    src_other = await _make_source(db_session, "https://other.com/feed.xml")
    await _link(db_session, user=user, source=src_subscribed, category=cat)

    a1 = await _add_article(db_session, source=src_subscribed, title="A1", minutes_ago=10)
    a2 = await _add_article(db_session, source=src_subscribed, title="A2", minutes_ago=20)
    await _add_article(db_session, source=src_other, title="X", minutes_ago=5)
    await db_session.commit()

    rows, _ = await articles_service.timeline_for_user(
        db_session, user_id=int(user.id), limit=50
    )
    ids = [int(r.article.id) for r in rows]
    assert int(a1.id) in ids
    assert int(a2.id) in ids
    # Articolo della source non sottoscritta NON deve esserci
    assert all(r.source.id != src_other.id for r in rows)


async def test_timeline_for_user_skips_non_indexed(db_session) -> None:
    user = await _make_user(db_session, username="bob")
    cat = await _make_category(db_session, user=user, name="C", public=True)
    src = await _make_source(db_session, "https://b.com/feed.xml")
    await _link(db_session, user=user, source=src, category=cat)

    a_indexed = await _add_article(db_session, source=src, title="OK", minutes_ago=1, indexed=True)
    a_pending = await _add_article(db_session, source=src, title="PENDING", minutes_ago=2, indexed=False)
    await db_session.commit()

    rows, _ = await articles_service.timeline_for_user(
        db_session, user_id=int(user.id), limit=50
    )
    ids = [int(r.article.id) for r in rows]
    assert int(a_indexed.id) in ids
    assert int(a_pending.id) not in ids


async def test_timeline_for_user_orders_desc_and_paginates(db_session) -> None:
    user = await _make_user(db_session, username="carol")
    cat = await _make_category(db_session, user=user, name="C", public=True)
    src = await _make_source(db_session, "https://c.com/feed.xml")
    await _link(db_session, user=user, source=src, category=cat)

    # Crea 5 articoli con published_at decrescenti (1m, 2m, 3m, 4m, 5m fa)
    arts = []
    for i in range(5):
        arts.append(
            await _add_article(
                db_session, source=src, title=f"A{i}", minutes_ago=i + 1
            )
        )
    await db_session.commit()

    # Pagina 1: limite 3
    page1, cursor = await articles_service.timeline_for_user(
        db_session, user_id=int(user.id), limit=3
    )
    assert len(page1) == 3
    # Più recenti per primi
    titles = [(r.article.raw_meta_lite or {}).get("title") for r in page1]
    assert titles == ["A0", "A1", "A2"]
    assert cursor is not None

    # Pagina 2: con cursor
    page2, cursor2 = await articles_service.timeline_for_user(
        db_session, user_id=int(user.id), cursor=cursor, limit=3
    )
    titles_2 = [(r.article.raw_meta_lite or {}).get("title") for r in page2]
    assert titles_2 == ["A3", "A4"]
    assert cursor2 is None


# ---------------------------------------------------------------------------
# timeline_for_public_user (filtra su Category.is_public)
# ---------------------------------------------------------------------------


async def test_timeline_for_public_user_filters_private_categories(db_session) -> None:
    user = await _make_user(db_session, username="dave")
    cat_pub = await _make_category(db_session, user=user, name="Pub", public=True)
    cat_priv = await _make_category(db_session, user=user, name="Priv", public=False)

    src_pub = await _make_source(db_session, "https://pub.com/feed.xml")
    src_priv = await _make_source(db_session, "https://priv.com/feed.xml")
    await _link(db_session, user=user, source=src_pub, category=cat_pub)
    await _link(db_session, user=user, source=src_priv, category=cat_priv)

    a_pub = await _add_article(db_session, source=src_pub, title="PubArt", minutes_ago=1)
    await _add_article(db_session, source=src_priv, title="PrivArt", minutes_ago=2)
    await db_session.commit()

    rows, _ = await articles_service.timeline_for_public_user(
        db_session, target_user_id=int(user.id), limit=50
    )
    ids = [int(r.article.id) for r in rows]
    assert int(a_pub.id) in ids
    assert all((r.article.raw_meta_lite or {}).get("title") != "PrivArt" for r in rows)


# ---------------------------------------------------------------------------
# timeline_for_user — filtro category_id (F-001)
# ---------------------------------------------------------------------------


async def test_timeline_for_user_filters_by_category(db_session) -> None:
    """Solo articoli delle source linkate a quella categoria."""
    user = await _make_user(db_session, username="kim")
    cat_a = await _make_category(db_session, user=user, name="A", public=True)
    cat_b = await _make_category(db_session, user=user, name="B", public=True)

    src_a = await _make_source(db_session, "https://a.com/feed.xml")
    src_b = await _make_source(db_session, "https://b.com/feed.xml")
    await _link(db_session, user=user, source=src_a, category=cat_a)
    await _link(db_session, user=user, source=src_b, category=cat_b)

    art_a = await _add_article(db_session, source=src_a, title="A1", minutes_ago=5)
    art_b = await _add_article(db_session, source=src_b, title="B1", minutes_ago=10)
    await db_session.commit()

    rows, _ = await articles_service.timeline_for_user(
        db_session, user_id=int(user.id), category_id=int(cat_a.id), limit=50
    )
    ids = [int(r.article.id) for r in rows]
    assert int(art_a.id) in ids
    assert int(art_b.id) not in ids


async def test_timeline_for_user_filters_includes_subcategories(db_session) -> None:
    """Filtro su categoria root → include articoli da source linkate alla
    sotto-categoria."""
    user = await _make_user(db_session, username="leo")
    root = await _make_category(db_session, user=user, name="Root", public=True)
    # crea sotto-categoria figlia di root
    from app.models import Category

    child = Category(
        user_id=user.id,
        name="Child",
        slug="child",
        parent_id=root.id,
        is_public=True,
        position=0,
    )
    db_session.add(child)
    await db_session.flush()

    src_root = await _make_source(db_session, "https://root.com/feed.xml")
    src_child = await _make_source(db_session, "https://child.com/feed.xml")
    await _link(db_session, user=user, source=src_root, category=root)
    await _link(db_session, user=user, source=src_child, category=child)

    art_root = await _add_article(db_session, source=src_root, title="Root1", minutes_ago=1)
    art_child = await _add_article(db_session, source=src_child, title="Child1", minutes_ago=2)
    await db_session.commit()

    rows, _ = await articles_service.timeline_for_user(
        db_session, user_id=int(user.id), category_id=int(root.id), limit=50
    )
    ids = [int(r.article.id) for r in rows]
    assert int(art_root.id) in ids
    assert int(art_child.id) in ids


async def test_timeline_for_user_filter_by_topic(db_session) -> None:
    """Filtro `topic_id` ritorna solo articoli che hanno quel topic in
    `article_topics`."""
    user = await _make_user(db_session, username="topf")
    cat = await _make_category(db_session, user=user, name="C", public=True)
    src = await _make_source(db_session, "https://t.com/feed.xml")
    await _link(db_session, user=user, source=src, category=cat)

    [t_apple, t_other] = await _make_topics(db_session, "Apple", "OtherBrand")

    art_a = await _add_article(db_session, source=src, title="HasApple", minutes_ago=1)
    art_b = await _add_article(db_session, source=src, title="NoApple", minutes_ago=2)
    art_c = await _add_article(db_session, source=src, title="OtherOnly", minutes_ago=3)
    await _link_topics(db_session, article_id=int(art_a.id), topic_ids=[int(t_apple.id), int(t_other.id)])
    await _link_topics(db_session, article_id=int(art_c.id), topic_ids=[int(t_other.id)])
    await db_session.commit()

    rows, _ = await articles_service.timeline_for_user(
        db_session, user_id=int(user.id), topic_id=int(t_apple.id), limit=50
    )
    ids = [int(r.article.id) for r in rows]
    assert int(art_a.id) in ids
    assert int(art_b.id) not in ids
    assert int(art_c.id) not in ids


async def test_timeline_for_user_filter_rejects_other_users_category(db_session) -> None:
    """Sicurezza: l'utente non può usare un category_id che non gli appartiene."""
    alice = await _make_user(db_session, username="alice2")
    bob = await _make_user(db_session, username="bob2")
    bob_cat = await _make_category(db_session, user=bob, name="BobC", public=True)
    bob_src = await _make_source(db_session, "https://bob.com/feed.xml")
    await _link(db_session, user=bob, source=bob_src, category=bob_cat)
    await _add_article(db_session, source=bob_src, title="Bob1", minutes_ago=1)
    await db_session.commit()

    # Alice prova ad usare la category di Bob → 0 risultati (security)
    rows, _ = await articles_service.timeline_for_user(
        db_session, user_id=int(alice.id), category_id=int(bob_cat.id), limit=50
    )
    assert rows == []


# ---------------------------------------------------------------------------
# timeline_global_public (vetrina home: aggrega TUTTE le categorie pubbliche)
# ---------------------------------------------------------------------------


async def test_timeline_global_public_aggregates_across_users(db_session) -> None:
    """Articoli da utenti diversi con categorie pubbliche convergono nella
    stessa vetrina."""
    eve = await _make_user(db_session, username="eve")
    eve_pub = await _make_category(db_session, user=eve, name="EvePub", public=True)
    src_eve = await _make_source(db_session, "https://eve.com/feed.xml")
    await _link(db_session, user=eve, source=src_eve, category=eve_pub)

    frank = await _make_user(db_session, username="frank")
    frank_pub = await _make_category(db_session, user=frank, name="FrankPub", public=True)
    src_frank = await _make_source(db_session, "https://frank.com/feed.xml")
    await _link(db_session, user=frank, source=src_frank, category=frank_pub)

    art_eve = await _add_article(db_session, source=src_eve, title="EveArt", minutes_ago=10)
    art_frank = await _add_article(db_session, source=src_frank, title="FrankArt", minutes_ago=20)
    await db_session.commit()

    rows = await articles_service.timeline_global_public(db_session, limit=50)
    ids = [int(r.article.id) for r in rows]
    assert int(art_eve.id) in ids
    assert int(art_frank.id) in ids


async def test_timeline_global_public_excludes_private_categories(db_session) -> None:
    grace = await _make_user(db_session, username="grace")
    cat_pub = await _make_category(db_session, user=grace, name="P", public=True)
    cat_priv = await _make_category(db_session, user=grace, name="Q", public=False)
    src_pub = await _make_source(db_session, "https://gpub.com/feed.xml")
    src_priv = await _make_source(db_session, "https://gpriv.com/feed.xml")
    await _link(db_session, user=grace, source=src_pub, category=cat_pub)
    await _link(db_session, user=grace, source=src_priv, category=cat_priv)

    await _add_article(db_session, source=src_pub, title="GraceVisible", minutes_ago=5)
    await _add_article(db_session, source=src_priv, title="GraceHidden", minutes_ago=6)
    await db_session.commit()

    rows = await articles_service.timeline_global_public(db_session, limit=50)
    titles = [(r.article.raw_meta_lite or {}).get("title") for r in rows]
    assert "GraceVisible" in titles
    assert "GraceHidden" not in titles


async def test_timeline_global_public_dedups_shared_source(db_session) -> None:
    """Se la stessa source è linkata da due utenti pubblici, gli articoli non
    si duplicano nella vetrina (la subquery DISTINCT su source_id evita la
    moltiplicazione del JOIN su user_sources)."""
    h = await _make_user(db_session, username="hank")
    i = await _make_user(db_session, username="ivy")
    h_cat = await _make_category(db_session, user=h, name="H", public=True)
    i_cat = await _make_category(db_session, user=i, name="I", public=True)

    shared_src = await _make_source(db_session, "https://shared.com/feed.xml")
    await _link(db_session, user=h, source=shared_src, category=h_cat)
    await _link(db_session, user=i, source=shared_src, category=i_cat)

    art = await _add_article(db_session, source=shared_src, title="SharedArt", minutes_ago=1)
    await db_session.commit()

    rows = await articles_service.timeline_global_public(db_session, limit=50)
    occurrences = sum(1 for r in rows if int(r.article.id) == int(art.id))
    assert occurrences == 1, "L'articolo condiviso deve apparire una volta sola"


async def test_timeline_global_public_skips_non_indexed(db_session) -> None:
    j = await _make_user(db_session, username="judy")
    cat = await _make_category(db_session, user=j, name="J", public=True)
    src = await _make_source(db_session, "https://judy.com/feed.xml")
    await _link(db_session, user=j, source=src, category=cat)

    indexed = await _add_article(db_session, source=src, title="Ready", minutes_ago=1, indexed=True)
    pending = await _add_article(db_session, source=src, title="NotReady", minutes_ago=2, indexed=False)
    await db_session.commit()

    rows = await articles_service.timeline_global_public(db_session, limit=50)
    ids = [int(r.article.id) for r in rows]
    assert int(indexed.id) in ids
    assert int(pending.id) not in ids


# ---------------------------------------------------------------------------
# related_articles — F-005
# ---------------------------------------------------------------------------


async def _link_topics(db_session, *, article_id: int, topic_ids: list[int]) -> None:
    from app.models import ArticleTopic

    for tid in topic_ids:
        db_session.add(
            ArticleTopic(
                article_id=article_id,
                topic_id=tid,
                score=1.0,
                source="dict",
                position="title",
            )
        )
    await db_session.flush()


async def _make_topics(db_session, *names) -> list:
    from app.models import Topic

    out = []
    for n in names:
        t = Topic(
            type="brand",
            slug=n.lower().replace(" ", "-"),
            display_name=n,
            aliases=[],
            is_curated=True,
        )
        db_session.add(t)
        await db_session.flush()
        out.append(t)
    return out


async def test_related_articles_max_formula(db_session) -> None:
    user = await _make_user(db_session, username="rel1")
    cat = await _make_category(db_session, user=user, name="C", public=True)
    src = await _make_source(db_session, "https://r.com/feed.xml")
    await _link(db_session, user=user, source=src, category=cat)

    [t1, t2, t3] = await _make_topics(db_session, "Apple", "iPhone", "Tim Cook")

    # Source: 3 topics
    art_src = await _add_article(db_session, source=src, title="Src", minutes_ago=60 * 24)
    await _link_topics(db_session, article_id=int(art_src.id), topic_ids=[int(t1.id), int(t2.id), int(t3.id)])

    # Candidato A: 2/3 in comune con src → max formula = 2/max(3,2)=0.66 ≥ 0.6 ✓
    art_a = await _add_article(db_session, source=src, title="A", minutes_ago=60 * 12)
    await _link_topics(db_session, article_id=int(art_a.id), topic_ids=[int(t1.id), int(t2.id)])

    # Candidato B: 1/3 in comune → 1/max(3,1)=0.33 < 0.6 ✗
    art_b = await _add_article(db_session, source=src, title="B", minutes_ago=60 * 12)
    await _link_topics(db_session, article_id=int(art_b.id), topic_ids=[int(t1.id)])
    await db_session.commit()

    pairs = await articles_service.related_articles(
        db_session, article_id=int(art_src.id), days_window=15, min_overlap=0.6, formula="max"
    )
    ids = [int(r.article.id) for r, _ in pairs]
    assert int(art_a.id) in ids
    assert int(art_b.id) not in ids


async def test_related_articles_excludes_outside_time_window(db_session) -> None:
    user = await _make_user(db_session, username="rel2")
    cat = await _make_category(db_session, user=user, name="C", public=True)
    src = await _make_source(db_session, "https://r2.com/feed.xml")
    await _link(db_session, user=user, source=src, category=cat)

    [t1, t2] = await _make_topics(db_session, "Foo", "Bar")

    art_src = await _add_article(db_session, source=src, title="Src", minutes_ago=60)
    await _link_topics(db_session, article_id=int(art_src.id), topic_ids=[int(t1.id), int(t2.id)])

    # Articolo lontano nel tempo (60 giorni) — fuori finestra ±15
    art_far = await _add_article(
        db_session, source=src, title="Far", minutes_ago=60 * 24 * 60
    )
    await _link_topics(db_session, article_id=int(art_far.id), topic_ids=[int(t1.id), int(t2.id)])
    await db_session.commit()

    pairs = await articles_service.related_articles(
        db_session, article_id=int(art_src.id), days_window=15, min_overlap=0.6
    )
    ids = [int(r.article.id) for r, _ in pairs]
    assert int(art_far.id) not in ids


async def test_related_articles_jaccard_stricter_than_max(db_session) -> None:
    """jaccard = inter/union, max = inter/max(|A|,|B|). Su set di taglie diverse
    jaccard è più severo: A=3, B=10, inter=2 → max=2/10=0.2; jaccard=2/11=0.18."""
    user = await _make_user(db_session, username="rel3")
    cat = await _make_category(db_session, user=user, name="C", public=True)
    src = await _make_source(db_session, "https://r3.com/feed.xml")
    await _link(db_session, user=user, source=src, category=cat)

    topics = await _make_topics(db_session, "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11")
    src_topics = [int(t.id) for t in topics[:3]]   # |A| = 3

    art_src = await _add_article(db_session, source=src, title="Src", minutes_ago=60)
    await _link_topics(db_session, article_id=int(art_src.id), topic_ids=src_topics)

    # Candidato: 2 topic in comune + 8 altri → |B|=10, inter=2
    cand_topics = [int(topics[0].id), int(topics[1].id)] + [int(t.id) for t in topics[3:11]]
    art_cand = await _add_article(db_session, source=src, title="Cand", minutes_ago=120)
    await _link_topics(db_session, article_id=int(art_cand.id), topic_ids=cand_topics)
    await db_session.commit()

    # source = 2/3 = 0.66 >= 0.6 ✓
    src_pairs = await articles_service.related_articles(
        db_session, article_id=int(art_src.id), formula="source", min_overlap=0.6
    )
    src_ids = [int(r.article.id) for r, _ in src_pairs]
    assert int(art_cand.id) in src_ids

    # max = 2/10 = 0.2 < 0.6 ✗
    max_pairs = await articles_service.related_articles(
        db_session, article_id=int(art_src.id), formula="max", min_overlap=0.6
    )
    max_ids = [int(r.article.id) for r, _ in max_pairs]
    assert int(art_cand.id) not in max_ids

    # jaccard = 2/11 ≈ 0.18 < 0.6 ✗
    jac_pairs = await articles_service.related_articles(
        db_session, article_id=int(art_src.id), formula="jaccard", min_overlap=0.6
    )
    jac_ids = [int(r.article.id) for r, _ in jac_pairs]
    assert int(art_cand.id) not in jac_ids


async def test_related_articles_returns_empty_for_article_without_topics(db_session) -> None:
    user = await _make_user(db_session, username="rel4")
    cat = await _make_category(db_session, user=user, name="C", public=True)
    src = await _make_source(db_session, "https://r4.com/feed.xml")
    await _link(db_session, user=user, source=src, category=cat)

    art = await _add_article(db_session, source=src, title="NoTopics", minutes_ago=60)
    await db_session.commit()

    pairs = await articles_service.related_articles(
        db_session, article_id=int(art.id)
    )
    assert pairs == []


# ---------------------------------------------------------------------------
# get_article_detail (senza Manticore: docs vuoto è atteso)
# ---------------------------------------------------------------------------


async def test_get_article_detail_returns_none_for_missing_id(db_session) -> None:
    out = await articles_service.get_article_detail(db_session, article_id=999999)
    assert out is None
