"""Generazione sitemap.xml e robots.txt.

La sitemap include:
  - `/` (home)
  - tutti i profili pubblici `/{username}` (utenti con almeno una categoria
    pubblica)

`lastmod` per profilo = max(`articles.published_at`) tra le user_sources
dell'utente che vivono in una categoria pubblica. Se l'utente non ha articoli
ancora indicizzati, fallback a `users.created_at`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable
from xml.sax.saxutils import escape

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Article, Category, User, UserSource


@dataclass
class SitemapEntry:
    loc: str
    lastmod: datetime
    changefreq: str = "daily"
    priority: float = 0.5


async def collect_public_profile_entries(
    session: AsyncSession, *, base_url: str
) -> list[SitemapEntry]:
    """Ritorna entry sitemap per tutti gli utenti che hanno almeno una
    categoria pubblica con almeno una sorgente associata."""
    base = base_url.rstrip("/")

    # Subquery: tutti gli user_id distinti che hanno categorie pubbliche+sources
    public_users_q = (
        select(User.id, User.username, User.created_at)
        .join(Category, Category.user_id == User.id)
        .join(UserSource, UserSource.user_id == User.id)
        .where(Category.is_public.is_(True))
        .where(UserSource.category_id == Category.id)
        .group_by(User.id, User.username, User.created_at)
    )
    users = (await session.execute(public_users_q)).all()
    if not users:
        return []

    # Per ogni user, prendi max(published_at) sui suoi articoli (sources sue)
    user_ids = [u[0] for u in users]
    last_mod_q = (
        select(UserSource.user_id, func.max(Article.published_at))
        .join(Article, Article.source_id == UserSource.source_id)
        .join(Category, Category.id == UserSource.category_id)
        .where(UserSource.user_id.in_(user_ids))
        .where(Category.is_public.is_(True))
        .where(Article.processing_status == "indexed")
        .group_by(UserSource.user_id)
    )
    last_mod_rows = (await session.execute(last_mod_q)).all()
    last_mod_by_user: dict[int, datetime] = {
        int(uid): ts for uid, ts in last_mod_rows if ts is not None
    }

    out: list[SitemapEntry] = []
    for user_id, username, created_at in users:
        lm = last_mod_by_user.get(int(user_id)) or created_at or datetime.now(UTC)
        if lm.tzinfo is None:
            lm = lm.replace(tzinfo=UTC)
        out.append(
            SitemapEntry(
                loc=f"{base}/{username}",
                lastmod=lm,
                changefreq="hourly",
                priority=0.8,
            )
        )
    return out


def build_sitemap_xml(entries: Iterable[SitemapEntry]) -> str:
    """Costruisce il body sitemap (sitemaps.org schema 0.9)."""
    parts: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for e in entries:
        parts.append("  <url>")
        parts.append(f"    <loc>{escape(e.loc)}</loc>")
        parts.append(f"    <lastmod>{e.lastmod.astimezone(UTC).isoformat()}</lastmod>")
        parts.append(f"    <changefreq>{e.changefreq}</changefreq>")
        parts.append(f"    <priority>{e.priority:.1f}</priority>")
        parts.append("  </url>")
    parts.append("</urlset>")
    parts.append("")  # trailing newline
    return "\n".join(parts)


def build_robots_txt(*, base_url: str, allow_indexing: bool = True) -> str:
    base = base_url.rstrip("/")
    if not allow_indexing:
        # Staging: blocca tutto
        return "User-agent: *\nDisallow: /\n"

    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /yf_\n"
        "Disallow: /me/\n"
        "Disallow: /login\n"
        "Disallow: /register\n"
        "Disallow: /verify-email\n"
        "Disallow: /verify-email-pending\n"
        "Disallow: /static/\n"
        f"\nSitemap: {base}/sitemap.xml\n"
    )
