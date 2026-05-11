"""Unit test puri per app.services.seo_service (build_sitemap_xml + robots)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services import seo_service


def _entry(loc: str = "https://www.youfeed.it/foo", **kw: object) -> seo_service.SitemapEntry:
    base: dict = {
        "lastmod": datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        "changefreq": "daily",
        "priority": 0.5,
    }
    base.update(kw)
    return seo_service.SitemapEntry(loc=loc, **base)


# ---------------------------------------------------------------------------
# build_sitemap_xml
# ---------------------------------------------------------------------------


def test_sitemap_xml_has_xml_header_and_urlset_namespace() -> None:
    body = seo_service.build_sitemap_xml([_entry()])
    assert body.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"' in body
    assert "<urlset" in body and "</urlset>" in body


def test_sitemap_xml_contains_loc_lastmod_priority() -> None:
    body = seo_service.build_sitemap_xml(
        [_entry(loc="https://www.youfeed.it/drtarr", priority=0.8)]
    )
    assert "<loc>https://www.youfeed.it/drtarr</loc>" in body
    assert "<lastmod>2026-05-07T12:00:00+00:00</lastmod>" in body
    assert "<priority>0.8</priority>" in body


def test_sitemap_xml_escapes_special_chars_in_loc() -> None:
    body = seo_service.build_sitemap_xml([_entry(loc="https://x.com/?q=a&b=c")])
    assert "&amp;" in body
    assert "&b=c" not in body  # crudo non deve apparire


def test_sitemap_xml_with_multiple_entries() -> None:
    entries = [
        _entry(loc="https://www.youfeed.it/", priority=1.0, changefreq="hourly"),
        _entry(loc="https://www.youfeed.it/drtarr", priority=0.8),
        _entry(loc="https://www.youfeed.it/anotheruser", priority=0.8),
    ]
    body = seo_service.build_sitemap_xml(entries)
    assert body.count("<url>") == 3
    assert body.count("</url>") == 3


def test_sitemap_xml_with_empty_list() -> None:
    body = seo_service.build_sitemap_xml([])
    assert "<urlset" in body
    assert "<url>" not in body


def test_sitemap_xml_naive_lastmod_is_normalized_to_utc() -> None:
    naive = datetime(2026, 5, 7, 12, 0, tzinfo=UTC)
    body = seo_service.build_sitemap_xml([_entry(lastmod=naive)])
    assert "+00:00" in body


# ---------------------------------------------------------------------------
# build_robots_txt
# ---------------------------------------------------------------------------


def test_robots_disallows_internal_paths() -> None:
    body = seo_service.build_robots_txt(base_url="https://www.youfeed.it")
    assert "User-agent: *" in body
    assert "Disallow: /yf_" in body
    assert "Disallow: /me/" in body
    assert "Disallow: /login" in body
    assert "Disallow: /verify-email" in body
    assert "Sitemap: https://www.youfeed.it/sitemap.xml" in body


def test_robots_blocks_all_when_indexing_disabled() -> None:
    body = seo_service.build_robots_txt(
        base_url="https://staging.youfeed.it", allow_indexing=False
    )
    assert "Disallow: /\n" in body
    assert "Sitemap:" not in body  # in staging non esponiamo sitemap
