"""Rilevamento lingua di una fonte (euristica a stop-words, zero dipendenze).

YouFeed è IT-only: gli articoli di fonti in altra lingua (tipicamente
inglese) inquinerebbero topic e ricerca pubblica. Qui decidiamo la lingua
di una `Source` dai titoli dei suoi articoli; il pipeline usa il risultato
per escludere le fonti non italiane dall'engine (vedi `is_engine_language`).

L'euristica conta le stop-words per lingua sui titoli: titoli giornalistici
sono corti, ma su 10+ titoli il segnale è netto. Se il segnale è debole
ritorna `None` (= sconosciuta, trattata come italiana: nel dubbio non
escludiamo fonti legittime).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

ENGINE_LANG = "it"

_STOPWORDS: dict[str, frozenset[str]] = {
    "it": frozenset(
        "il lo la i gli le un una uno di del dello della dei degli delle a al "
        "alla ai alle da dal dalla in nel nella nei nelle con su sul sulla per "
        "tra fra e è ed che non come più anche dopo sono questo questa ecco "
        "perché cosa ha hanno essere nuovo nuova contro".split()
    ),
    "en": frozenset(
        "the of and to in is are for on with that this it as at by from be "
        "was were has have not you your how why what new after will can its "
        "an or but about more into over says".split()
    ),
    "es": frozenset(
        "el la los las de del y en un una es que por con para como más su al "
        "se lo".split()
    ),
    "fr": frozenset(
        "le la les des du de et en un une est que pour dans sur avec par au "
        "aux ce cette plus pas".split()
    ),
    "de": frozenset(
        "der die das den dem des und ist ein eine zu mit für auf von nicht "
        "im bei nach auch wie".split()
    ),
}

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# Servono abbastanza stop-words complessive per fidarsi del verdetto.
_MIN_HITS = 8
# La lingua vincente deve avere almeno questo rapporto sulla seconda.
_MIN_DOMINANCE = 1.5


def detect_language(texts: Iterable[str]) -> str | None:
    """Ritorna il codice lingua (`it`, `en`, `es`, `fr`, `de`) o None."""
    scores = dict.fromkeys(_STOPWORDS, 0)
    for text in texts:
        for w in _WORD_RE.findall((text or "").lower()):
            for lang, words in _STOPWORDS.items():
                if w in words:
                    scores[lang] += 1
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    (best, best_n), (_, second_n) = ranked[0], ranked[1]
    if best_n < _MIN_HITS:
        return None
    if second_n and best_n / second_n < _MIN_DOMINANCE:
        return None
    return best


def is_engine_language(lang: str | None) -> bool:
    """True se gli articoli della fonte vanno nell'engine (topic, ricerca
    pubblica, vetrina). Lingua sconosciuta = sì (non escludere nel dubbio)."""
    return lang is None or lang == ENGINE_LANG
