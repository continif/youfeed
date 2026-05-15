"""Generazione sitemap.xml e robots.txt.

La sitemap pubblicata è statica (6 entry curate) — NON include i profili
pubblici degli utenti: troppi falsi positivi per Google (account inattivi,
profili senza contenuto, churn). I profili restano comunque indicizzabili
dai motori se linkati dall'esterno.

Entry:
  /                  home, changefreq=hourly, lastmod=max(published_at)
  /register          changefreq=monthly
  /bot               changefreq=monthly
  /chi-siamo         changefreq=yearly
  /come-funziona     changefreq=yearly
  /disclaimer        changefreq=yearly
  /privacy           changefreq=yearly
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape


@dataclass
class SitemapEntry:
    loc: str
    lastmod: datetime
    changefreq: str = "daily"
    priority: float = 0.5


# I template Jinja delle info page vivono accanto a `templates/public/`.
# Usiamo l'mtime come `lastmod`: cambia ogni volta che riscriviamo la copy.
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "public"


def _template_lastmod(template_name: str, fallback: datetime) -> datetime:
    p = _TEMPLATES_DIR / template_name
    try:
        return datetime.fromtimestamp(p.stat().st_mtime, tz=UTC)
    except OSError:
        return fallback


def build_static_entries(
    *, base_url: str, home_lastmod: datetime
) -> list[SitemapEntry]:
    """Le 6 URL pubbliche che vogliamo nella sitemap."""
    base = base_url.rstrip("/")
    now = datetime.now(UTC)
    return [
        SitemapEntry(
            loc=base + "/",
            lastmod=home_lastmod,
            changefreq="hourly",
            priority=1.0,
        ),
        SitemapEntry(
            loc=base + "/register",
            lastmod=now,
            changefreq="monthly",
            priority=0.7,
        ),
        SitemapEntry(
            loc=base + "/bot",
            lastmod=_template_lastmod("bot.html", now),
            changefreq="monthly",
            priority=0.4,
        ),
        SitemapEntry(
            loc=base + "/chi-siamo",
            lastmod=_template_lastmod("chi-siamo.html", now),
            changefreq="yearly",
            priority=0.6,
        ),
        SitemapEntry(
            loc=base + "/come-funziona",
            lastmod=_template_lastmod("come-funziona.html", now),
            changefreq="yearly",
            priority=0.6,
        ),
        SitemapEntry(
            loc=base + "/disclaimer",
            lastmod=_template_lastmod("disclaimer.html", now),
            changefreq="yearly",
            priority=0.3,
        ),
        SitemapEntry(
            loc=base + "/privacy",
            lastmod=_template_lastmod("privacy.html", now),
            changefreq="yearly",
            priority=0.5,
        ),
    ]


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

    # NB: /register è ora indicizzabile (compare in sitemap), gli altri
    # flussi auth restano disallow per non disperdere crawl budget.
    # NIENTE Disallow: /static/ — Google ha bisogno di leggere CSS/JS per
    # renderizzare la pagina e valutarla (Mobile-Friendly + Core Web Vitals).
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /yf_\n"
        "Disallow: /me/\n"
        "Disallow: /login\n"
        "Disallow: /verify-email\n"
        "Disallow: /verify-email-pending\n"
        "Disallow: /forgot-password\n"
        "Disallow: /reset-password\n"
        f"\nSitemap: {base}/sitemap.xml\n"
    )
