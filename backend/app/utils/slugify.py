"""Slugify italiano-friendly. No dipendenze esterne."""

from __future__ import annotations

import re
import unicodedata


def slugify(value: str, *, max_length: int = 96) -> str:
    """Normalizza in lowercase ASCII, sostituisce spazi e punteggiatura con `-`.

    >>> slugify("Politica & Cronaca")
    'politica-cronaca'
    >>> slugify("Città   di Milano")
    'citta-di-milano'
    """
    if not value:
        return ""
    # Normalizza unicode (rimuove accenti)
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lower = ascii_only.lower()
    # Sostituisci tutto ciò che non è alfanumerico con "-"
    slug = re.sub(r"[^a-z0-9]+", "-", lower)
    slug = slug.strip("-")
    if max_length and len(slug) > max_length:
        slug = slug[:max_length].rstrip("-")
    return slug
