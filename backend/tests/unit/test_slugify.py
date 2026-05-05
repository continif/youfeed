"""Test slugify."""

from __future__ import annotations

import pytest

from app.utils.slugify import slugify


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Politica & Cronaca", "politica-cronaca"),
        ("Città di Milano", "citta-di-milano"),
        ("  spazi  ai  bordi  ", "spazi-ai-bordi"),
        ("ÀèÉìòù", "aeeiou"),
        ("Già Visto!", "gia-visto"),
        ("multi---trattini", "multi-trattini"),
        ("", ""),
        ("---", ""),
        ("L'Aquila", "l-aquila"),
    ],
)
def test_slugify_cases(raw: str, expected: str) -> None:
    assert slugify(raw) == expected


def test_slugify_max_length() -> None:
    long = "x" * 200
    s = slugify(long, max_length=10)
    assert len(s) <= 10
