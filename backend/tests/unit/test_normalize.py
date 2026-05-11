"""Unit test per app.ingestion.normalize (helper puri, no fetch HTTP)."""

from __future__ import annotations

from app.ingestion import normalize as nz


# ---------------------------------------------------------------------------
# _strip_html_to_text
# ---------------------------------------------------------------------------


def test_strip_html_to_text_basic() -> None:
    out = nz._strip_html_to_text("<p>Ciao <strong>mondo</strong></p>")
    # collapse whitespace per stabilità (selectolax inserisce spazi tra tag)
    assert " ".join(out.split()) == "Ciao mondo"


def test_strip_html_to_text_handles_empty() -> None:
    assert nz._strip_html_to_text("") == ""


def test_strip_html_to_text_strips_scripts() -> None:
    html = "<p>Testo</p><script>alert(1)</script>"
    out = nz._strip_html_to_text(html)
    assert "alert" not in out
    assert "Testo" in out


def test_strip_html_to_text_strips_inline_styles() -> None:
    html = "<style>.foo { color: red; }</style><p>Testo visibile</p>"
    out = nz._strip_html_to_text(html)
    assert "color" not in out
    assert ".foo" not in out
    assert "Testo visibile" in out


def test_strip_html_to_text_strips_noscript() -> None:
    html = (
        "<p>Articolo</p>"
        "<noscript>Questo sito richiede JavaScript abilitato</noscript>"
    )
    out = nz._strip_html_to_text(html)
    assert "JavaScript abilitato" not in out
    assert "Articolo" in out


def test_strip_html_to_text_strips_mixed_with_attributes() -> None:
    """script con attributi (type, src), style con media query, ecc."""
    html = """
        <article>
            <h1>Titolo articolo</h1>
            <script type="application/ld+json">{"@type":"Article"}</script>
            <style media="(min-width: 600px)">body { background: white }</style>
            <p>Corpo dell'articolo</p>
            <script src="https://cdn.example.com/tracker.js" async></script>
        </article>
    """
    out = nz._strip_html_to_text(html)
    assert "ld+json" not in out
    assert "background" not in out
    assert "tracker" not in out
    assert "Titolo articolo" in out
    assert "Corpo dell'articolo" in out


def test_strip_html_to_text_falls_back_to_regex_on_parse_error() -> None:
    """Anche con HTML estremamente malformato la funzione non solleva."""
    out = nz._strip_html_to_text("<p>ok</p" + "<" * 1000)
    assert "ok" in out


def test_strip_html_to_text_handles_double_encoded_tags() -> None:
    """Molti feed RSS hanno tag HTML-encoded come testo (`&lt;strong&gt;`).
    Il primo parse decodifica le entity, il secondo rimuove i tag emersi."""
    html = (
        "<div>La &lt;strong&gt;Jeep Avenger&lt;/strong&gt; è tra "
        "i &lt;b&gt;modelli&lt;/b&gt; più venduti.</div>"
    )
    out = nz._strip_html_to_text(html)
    assert "<strong>" not in out
    assert "</strong>" not in out
    assert "<b>" not in out
    assert "Jeep Avenger" in out
    assert "modelli" in out


def test_strip_html_to_text_handles_double_encoded_with_script() -> None:
    """Caso peggiore: script HTML-encoded dentro il body."""
    html = "<p>OK</p>&lt;script&gt;alert(1)&lt;/script&gt;"
    out = nz._strip_html_to_text(html)
    assert "<script" not in out
    # alert(1) appare come testo (il secondo parse non ha più tag da rimuovere
    # dentro un blob testuale): è un compromesso accettabile, l'attaccante non
    # può iniettare HTML eseguibile via questo path.


# ---------------------------------------------------------------------------
# _sanitize_html (whitelist tag + attributi)
# ---------------------------------------------------------------------------


def test_sanitize_html_drops_script() -> None:
    html = '<p>OK</p><script>evil()</script>'
    safe = nz._sanitize_html(html)
    assert "<script" not in safe.lower()
    assert "OK" in safe


def test_sanitize_html_drops_event_handlers() -> None:
    html = '<a href="x" onclick="evil()">link</a>'
    safe = nz._sanitize_html(html)
    assert "onclick" not in safe.lower()
    assert 'href="x"' in safe


def test_sanitize_html_keeps_allowed_tags() -> None:
    html = "<p><strong>grassetto</strong> e <em>corsivo</em></p>"
    safe = nz._sanitize_html(html)
    assert "<strong>" in safe
    assert "<em>" in safe


def test_sanitize_html_strips_disallowed_tags() -> None:
    # iframe non è nella whitelist
    safe = nz._sanitize_html("<iframe src='x'></iframe><p>resto</p>")
    assert "<iframe" not in safe.lower()
    assert "resto" in safe


# ---------------------------------------------------------------------------
# _extract_internal_links (filtra solo link allo stesso host del base_url)
# ---------------------------------------------------------------------------


def test_extract_internal_links_filters_external() -> None:
    html = """
        <a href="/articolo-2">Interno</a>
        <a href="https://altro-sito.com/x">Esterno</a>
        <a href="https://example.com/articolo-3">Stesso host</a>
    """
    out = nz._extract_internal_links(html, "https://example.com/articolo-1")
    urls = [item["url"] for item in out]
    assert "https://example.com/articolo-2" in urls
    assert "https://example.com/articolo-3" in urls
    assert all("altro-sito.com" not in u for u in urls)


def test_extract_internal_links_dedupes() -> None:
    html = '<a href="/a">A</a><a href="/a">A2</a><a href="/b">B</a>'
    out = nz._extract_internal_links(html, "https://example.com/x")
    urls = [item["url"] for item in out]
    assert urls.count("https://example.com/a") == 1


def test_extract_internal_links_empty_html() -> None:
    assert nz._extract_internal_links("", "https://example.com") == []
    assert nz._extract_internal_links("<p>solo testo</p>", "https://example.com") == []


def test_extract_internal_links_caps_at_20() -> None:
    links = "".join(f'<a href="/p{i}">{i}</a>' for i in range(40))
    out = nz._extract_internal_links(links, "https://example.com")
    assert len(out) <= 20


# ---------------------------------------------------------------------------
# _og_image_from_html
# ---------------------------------------------------------------------------


def test_og_image_from_html_property() -> None:
    html = '<html><head><meta property="og:image" content="/img.jpg"></head></html>'
    out = nz._og_image_from_html(html, "https://example.com/path")
    assert out == "https://example.com/img.jpg"


def test_og_image_falls_back_to_twitter() -> None:
    html = '<head><meta name="twitter:image" content="https://cdn.x.com/y.png"></head>'
    out = nz._og_image_from_html(html, "https://example.com")
    assert out == "https://cdn.x.com/y.png"


def test_og_image_returns_none_when_missing() -> None:
    assert nz._og_image_from_html("<html></html>", "https://x.com") is None
