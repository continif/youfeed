"""Estrattore regex di candidate topic.

Pattern per ner_type:
    REGEX_PER          → 2-4 token capitalizzati (Donald J. Trump, JD Vance)
    REGEX_POPE         → "Papa <Nome>..." con eventuale numero romano
    REGEX_BRAND_ALPHA  → 7Up, 3M, O2, BMW, IBM (alfanumerici/sigle)
    REGEX_BRAND_SINGLE → Adidas, Apple (parola singola in mid-sentence)
    REGEX_MODEL        → Brand + numero/parola (richiede whitelist brand)

L'estrazione e' una **prima passata permissiva**: salviamo TUTTO in `entities`
con un counter, l'umano in `cli review` decide il `topics.type` finale.

Convenzioni:
- Le funzioni `extract_*` ritornano lista di `Candidate` (forma puntuale,
  non aggregata). Caller fa l'aggregazione e l'upsert su DB.
- Tutti i pattern sono compilati una volta a load-time (modulo `_C`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

NER_TYPES: tuple[str, ...] = (
    "REGEX_PER",
    "REGEX_POPE",
    "REGEX_BRAND_ALPHA",
    "REGEX_BRAND_SINGLE",
    "REGEX_MODEL",
)


@dataclass(frozen=True)
class Candidate:
    """Match grezzo: surface_form (caratteri originali) + ner_type."""

    surface_form: str
    ner_type: str


def normalize(s: str) -> str:
    """Lowercase + collapse whitespace. Chiave per `entities.normalized`."""
    return re.sub(r"\s+", " ", s.strip()).lower()


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

# Lettere italiane: ASCII + accenti tipici. NON includiamo apostrofo perché
# rompe `\b` quando vorremmo matchare "L'Aquila".
_LETTER_LO = r"a-zàèéìòù"
_LETTER_UP = r"A-ZÀÈÉÌÒÙ"

# Token "pieno": maiuscola seguita da almeno 3 minuscole/accentate -> 4+ char.
_WORD_FULL = rf"[{_LETTER_UP}][{_LETTER_LO}]{{3,}}"
# Iniziale puntata: J., A.
_WORD_INITIAL = rf"[{_LETTER_UP}]\."
# Sigla: 2-5 maiuscole. NON deve essere seguita da minuscole (altrimenti
# sarebbe parte di una full word).
_WORD_SIGLA = rf"[{_LETTER_UP}]{{2,5}}(?![{_LETTER_LO}])"

# Sigle italiane comuni che NON sono persone/brand: preposizioni articulate
# ALL-CAPS in titoli (rare ma capitano). Filtrate post-match.
_SIGLA_BLACKLIST: frozenset[str] = frozenset(
    {
        "DI", "DEL", "DEI", "DELLA", "DELLE", "DA", "DAL", "DAI",
        "DALLE", "AL", "ALLA", "ALLE", "AI", "SU", "SUL", "SUI", "SULLA",
        "SULLE", "NEL", "NEI", "NELLA", "NELLE", "PER", "CON", "TRA", "FRA",
        "IL", "LO", "LA", "LE", "I", "GLI", "UN", "UNO", "UNA",
        "ED", "OD", "MA", "SE", "CHE", "CHI", "CUI", "NON",
        # Mesi capitalizzati per errore
        "GENNAIO", "FEBBRAIO", "MARZO", "APRILE", "MAGGIO", "GIUGNO",
        "LUGLIO", "AGOSTO", "SETTEMBRE", "OTTOBRE", "NOVEMBRE", "DICEMBRE",
        # Giorni
        "LUNEDI", "MARTEDI", "MERCOLEDI", "GIOVEDI", "VENERDI", "SABATO",
        "DOMENICA",
    }
)

# Parole singole capitalizzate da escludere come BRAND_SINGLE / FIRST_PERSON.
# Se compaiono come PRIMO token di un match PERSON, vengono trimmate
# (es. "Anche Mario Rossi" → "Mario Rossi"). Lista da espandere nel tempo.
#
# Cosa NON va qui: nomi di città/regioni (Milano, Roma, ...) e brand veri —
# quelli vivono come `topics(type='location'|'brand', is_curated=true)` e li
# scarta il filtro a valle (review CLI mostra `subtoken_topics` hint per i
# duplicati). Qui mettiamo solo sostantivi/aggettivi/voci-verbali italiani
# comuni che capitano capitalizzati per inizio frase o enfasi titolare.
_BRAND_SINGLE_BLACKLIST: frozenset[str] = frozenset(
    {
        # Avverbi/connettivi comuni in posizione iniziale
        "Inoltre", "Tuttavia", "Quindi", "Pertanto", "Ovvero", "Cioè",
        "Anche", "Ancora", "Sempre", "Dunque", "Allora", "Quando",
        "Mentre", "Prima", "Dopo", "Durante", "Verso", "Senza", "Sotto",
        "Sopra", "Dentro", "Fuori",
        "Soltanto", "Solo", "Solamente", "Subito", "Adesso", "Ormai",
        "Davvero", "Veramente", "Ovviamente", "Probabilmente", "Sicuramente",
        "Praticamente", "Finalmente", "Persino", "Eppure", "Nonostante",
        "Ovunque", "Dovunque", "Insieme", "Specialmente", "Soprattutto",
        "Comunque", "Magari", "Forse", "Quasi", "Almeno", "Talmente",
        "Tanto", "Molto", "Poco", "Tutto", "Niente", "Nulla", "Qualcosa",
        "Tutti", "Tutta", "Tutte",
        "Ecco", "Così", "Però", "Mai", "Spesso", "Talvolta", "Raramente",
        "Poi", "Ora", "Oggi", "Ieri", "Domani",
        # Voci verbali capitalizzate frequenti (passato remoto / 3sg presente)
        "Disse", "Parlò", "Iniziò", "Tornò", "Arrivò", "Entrò", "Uscì",
        "Andò", "Decise", "Vide", "Trovò", "Pensò", "Diede", "Mise",
        "Sembra", "Resta", "Diventa", "Crolla", "Rende", "Costa", "Vuole",
        "Manda", "Mette", "Toglie", "Apre", "Chiude", "Sale", "Scende",
        "Vince", "Perde", "Conferma", "Annuncia", "Smentisce", "Replica",
        "Risponde", "Difende", "Attacca", "Critica", "Promette", "Lancia",
        "Presenta", "Propone", "Lascia", "Continua", "Pubblica", "Mostra",
        "Spiega", "Racconta", "Dichiara", "Aggiunge", "Conclude", "Avverte",
        "Riporta", "Sostiene", "Ammette", "Insiste", "Ribadisce", "Punta",
        "Spera", "Teme", "Aspetta", "Cerca", "Prova", "Tenta",
        "Nasce", "Muore", "Vive", "Parte", "Arriva", "Inizia",
        "Finisce", "Cambia", "Cresce", "Cala", "Aumenta", "Diminuisce",
        "Pubblicato", "Pubblicata", "Annunciato", "Annunciata", "Confermato",
        "Confermata", "Atteso", "Attesa", "Voluto", "Voluta",
        # Verbi 3pl (frequenti nei titoli di articoli di cronaca/economia)
        "Crescono", "Vincono", "Perdono", "Salgono", "Scendono",
        "Sembrano", "Restano", "Diventano", "Crollano", "Scoppiano",
        "Vogliono", "Devono", "Possono", "Sanno", "Dicono", "Pensano",
        "Aprono", "Chiudono", "Guidano", "Trovano", "Decidono",
        "Annunciano", "Confermano", "Smentiscono", "Replicano",
        # Sostantivi italiani frequenti capitalizzati per enfasi titolo
        "Accordo", "Accordi", "Norma", "Norme", "Corte", "Corti",
        "Reddito", "Redditi", "Giro", "Giri", "Patto", "Patti",
        "Trattato", "Trattati", "Decreto", "Decreti", "Legge", "Leggi",
        "Riforma", "Riforme", "Direttiva", "Direttive", "Alba", "Albe",
        # Suffissi/qualifiche prodotto (entrano correttamente solo via REGEX_MODEL
        # con whitelist brand; come BRAND_SINGLE singolo sono FP)
        "Watch", "Mini", "Pro", "Plus", "Max", "Ultra", "Lite", "Series",
        "Gaming", "Demand", "Edition", "Premium", "Standard",
        # Termini geografici ambigui (Italia da sola è troppo generica per BRAND)
        "Italia", "Europa",
        # Componenti di location multi-parola: vengono già matchati come frase
        # dal dict (es. "Regno Unito"), ma BRAND_SINGLE li ripeschi singolarmente
        # come falsi positivi.
        "Regno", "Unito",
        # Sostantivi giornalistici/finanziari generici
        "Fonte", "Fonti", "Sostegno", "Cassa",
        # Sostantivi italiani plurali generici ("gli Stati europei", "i Paesi NATO")
        "Stati", "Paesi",
        # Comuni IT con nome = pronome/avverbio italiano comune (T-014):
        # Mira (VE) / verbo "mira", Alto (CN) / aggettivo, Posta (RI) / sostantivo.
        # `Ne` (GE) è < 4 char e non matcha BRAND_SINGLE, gestito solo dal dict.
        "Mira", "Alto", "Posta",
        # Round 3 (T-015, sample art. 27787): comuni IT con nome = sostantivo/
        # aggettivo italiano comune. Acuto/Casella/Front/Licenza/Matrice/Mese/Quindici.
        "Acuto", "Casella", "Front", "Licenza", "Matrice", "Mese", "Quindici",
        # Round 4 (T-016, sample art. 27451):
        # "Uniti" (plurale di Unito già in blacklist), nav-words tipo "Home",
        # voci verbali "Punti", parole UI form newsletter "Iscriviti"/"Invia".
        # "Home" appare in breadcrumb ("Home > Quantum"), il fix `_html_to_text`
        # le rimuove ma le terremmo anche qui per sicurezza in caso di nuovo
        # rumore HTML non-strutturato.
        "Uniti", "Home", "Punti", "Iscriviti", "Invia",
        # Round 5: sostantivi/voci verbali italiane comuni
        # Paese ("il Paese"), Siano (congiuntivo "essere" 3pl),
        # Data ("la data"), State ("siete state" / English noun).
        "Paese", "Siano", "Data", "State",
        # Categorie sportive/discipline che non vanno come brand
        "Formula", "Champions", "Coppa", "Mondiale", "Mondiali",
        "Bomba", "Bombe", "Boom", "Bombetta",
        "Fascia", "Canale", "Campagna", "Strada", "Storia", "Famiglia",
        "Festa", "Fortuna", "Sorpresa", "Scoperta", "Indagine",
        "Polemica", "Scandalo", "Sciopero", "Manovra", "Ripresa", "Crescita",
        "Calo", "Crollo", "Allarme", "Ondata", "Stretta", "Svolta", "Corsa",
        "Attacco", "Difesa", "Vittoria", "Sconfitta", "Pareggio",
        "Squadra", "Campionato", "Finale", "Maglia", "Stadio", "Coppa",
        "Premio", "Concorso", "Festival", "Edizione", "Stagione",
        "Settimana", "Mese", "Anno", "Decennio", "Secolo",
        "Mattina", "Mattino", "Pomeriggio", "Sera", "Notte",
        "Pasqua", "Natale", "Carnevale", "Capodanno", "Ferragosto",
        "Mappa", "Schema", "Tabella", "Lista", "Classifica", "Ranking",
        "Voto", "Sondaggio", "Studio", "Ricerca", "Inchiesta", "Reportage",
        "Speciale", "Dossier", "Approfondimento", "Servizio",
        "Tribunale", "Procura", "Sentenza", "Processo", "Udienza",
        "Vertice", "Riunione", "Incontro", "Visita", "Viaggio", "Missione",
        "Trasferta", "Conferenza", "Convegno", "Forum", "Summit",
        "Mercato", "Borsa", "Quotazione", "Azione", "Investimento",
        "Risparmio", "Spesa", "Costo", "Prezzo", "Sconto", "Offerta", "Offerte",
        "Promozione", "Promozioni", "Bonus", "Risarcimento", "Indennizzo", "Multa",
        "Sanzione", "Tassa", "Imposta", "Tariffa", "Bolletta", "Fattura",
        "Buono", "Voucher", "Conto", "Bilancio", "Trimestrale", "Semestrale",
        "Annuncio", "Comunicato", "Lettera", "Messaggio",
        "Audio", "Video", "Foto", "Immagine", "Bandiera", "Simbolo",
        "Logo", "Marchio", "Brevetto", "Licenza", "Permesso", "Concessione",
        "Appalto", "Gara", "Bando", "Selezione", "Esame", "Quiz",
        "Sfida", "Duello", "Lotta", "Battaglia", "Scontro", "Conflitto",
        "Crisi", "Emergenza", "Pericolo", "Rischio", "Minaccia", "Avviso",
        "Avvertimento", "Notifica", "Avvio", "Lancio", "Partenza",
        "Apertura", "Chiusura", "Fine", "Conclusione", "Termine", "Scadenza",
        "Limite", "Soglia", "Numero", "Cifra", "Quantità", "Quota",
        "Doppio", "Triplo", "Totale", "Somma", "Differenza",
        "Caso", "Vicenda", "Episodio", "Capitolo", "Pagina", "Articolo",
        "Notizia", "News", "Rassegna",
        "Banco", "Tavolo", "Sedia", "Porta", "Finestra", "Stanza", "Sala",
        "Casa", "Villa", "Palazzo", "Edificio", "Ufficio", "Sede",
        "Centro", "Punto", "Posto", "Luogo", "Zona", "Area", "Quartiere",
        "Lavoro", "Salute", "Sanità", "Scuola", "Cultura", "Sport",
        "Musica", "Cinema", "Teatro", "Web",
        "Mondo", "Paese", "Estero", "Estate", "Autunno", "Inverno", "Primavera",
        # Aggettivi superlativi/qualificativi capitalizzati per enfasi
        "Nuovo", "Nuova", "Nuovi", "Nuove", "Vecchio", "Vecchia",
        "Grande", "Grandi", "Piccolo", "Piccola",
        "Buona", "Cattivo", "Cattiva",
        "Bello", "Bella", "Belli", "Belle", "Brutto", "Brutta",
        "Ottimo", "Ottima", "Pessimo", "Pessima", "Migliore", "Peggiore",
        "Massimo", "Massima", "Minimo", "Minima",
        "Primo", "Secondo", "Seconda", "Terzo", "Terza",
        "Ultimo", "Ultima", "Penultimo",
        # Pronomi/determinanti che capitano capitalizzati (errori OCR/HTML)
        "Dello", "Della", "Delle", "Degli", "Sullo", "Sulla", "Sulle",
        "Sugli", "Nello", "Nella", "Nelle", "Negli", "Quello", "Quella",
        "Quelli", "Quelle", "Questo", "Questa", "Questi", "Queste",
        "Stesso", "Stessa", "Stessi", "Stesse",
        # Mesi capitalizzati per errore (in italiano i mesi sono lower)
        "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
        "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
        # Giorni
        "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato",
        "Domenica",
    }
)

# Numeri romani (per i papi) — fino a XVIII coperto i papi storici.
_ROMAN = r"(?:I{1,3}|IV|V|VI{1,3}|IX|X{1,3}|XL|L|XC|C{1,3}|CD|D|XVI{1,3}|XVII|XVIII|XIX|XX)"


# ---------------------------------------------------------------------------
# Pattern compilati
# ---------------------------------------------------------------------------


# 1) PERSON: 2-4 token, FIRST = full|sigla, MIDDLE = full|initial|sigla,
#    LAST = full. Usiamo gruppi per estrarre.
_RE_PERSON = re.compile(
    rf"""
    \b
    ( (?: {_WORD_FULL} | {_WORD_SIGLA} ) )         # FIRST
    \s+
    (?: (?: {_WORD_FULL} | {_WORD_INITIAL} | {_WORD_SIGLA} ) \s+ ){{0,2}}
    ( {_WORD_FULL} )                                # LAST (per gruppo finale)
    \b
    """,
    re.VERBOSE,
)

# 2) POPE: "Papa <NomeFull> [NomeFull [NomeFull]] [Roman]"
# Per i papi allentiamo la soglia minima a 3 char totali (Pio, Leo) — l'anchor
# "Papa" rende il falso positivo molto improbabile.
_WORD_FULL_POPE = rf"[{_LETTER_UP}][{_LETTER_LO}]{{2,}}"
_RE_POPE = re.compile(
    rf"""
    \b Papa \s+
    {_WORD_FULL_POPE}
    (?: \s+ {_WORD_FULL_POPE} ){{0,2}}
    (?: \s+ {_ROMAN} )?
    \b
    """,
    re.VERBOSE,
)

# 3) BRAND_ALPHA: 7Up, 3M, O2, BMW, IBM. Tre sotto-pattern.
_RE_BRAND_ALPHA = re.compile(
    rf"""
    \b
    (
        \d+ [{_LETTER_UP}] [{_LETTER_LO}]*           # 7Up, 3M
      | [{_LETTER_UP}][{_LETTER_LO}]* \d+            # F1, K2
      | [{_LETTER_UP}]+ \d+                          # O2, A4
      | [{_LETTER_UP}]{{2,5}} (?![{_LETTER_LO}])     # BMW, IBM, RAI
    )
    \b
    """,
    re.VERBOSE,
)

# 4) BRAND_SINGLE: parola singola capitalizzata 4+ char, **mid-sentence**:
#    preceduta da una lettera minuscola/accentata o da virgola/`;`/`:` + spazio
#    (NON da inizio testo, NON da `.` `?` `!`).
_RE_BRAND_SINGLE = re.compile(
    rf"""
    (?<= [{_LETTER_LO},;:] \  )                     # backref char + spazio (lookbehind fix-len)
    ( {_WORD_FULL} )
    \b
    """,
    re.VERBOSE,
)


# ---------------------------------------------------------------------------
# Public extractors
# ---------------------------------------------------------------------------


def extract_persons(text: str) -> list[Candidate]:
    if not text:
        return []
    text = text + " "  # garantisce boundary per nomi a fine stringa
    out: list[Candidate] = []
    for m in _RE_PERSON.finditer(text):
        surface = m.group(0).strip()
        if _person_has_blacklisted_sigla(surface):
            continue
        # Trim parole italiane comuni capitalizzate da entrambi i lati:
        # "Anche Mario Rossi Disse" → "Mario Rossi". Loop iterativi gestiscono
        # multi-token leading/trailing tipo "Inoltre Anche Mario Rossi Disse Punti".
        surface = _trim_blacklisted_edge_tokens(surface)
        if surface is None:
            continue
        out.append(Candidate(surface_form=surface, ner_type="REGEX_PER"))
    return _dedupe_per_match(out)


def _trim_blacklisted_edge_tokens(surface: str) -> str | None:
    """Rimuove da TESTA e CODA i token in `_BRAND_SINGLE_BLACKLIST` (avverbi/
    voci verbali italiane comuni capitalizzate). Ritorna None se il
    rimanente non è più un nome valido (< 2 token, FIRST puntata, o LAST
    non full word).

    Esempio (testa): "Anche Mario Rossi" → "Mario Rossi".
    Esempio (coda):  "Pierluigi Sandonnini Punti" → "Pierluigi Sandonnini".
    """
    tokens = surface.split()
    while tokens and tokens[0] in _BRAND_SINGLE_BLACKLIST:
        tokens.pop(0)
    while tokens and tokens[-1] in _BRAND_SINGLE_BLACKLIST:
        tokens.pop()
    if len(tokens) < 2:
        return None
    # FIRST deve essere full o sigla, non un'iniziale puntata (es. "J.")
    if re.fullmatch(_WORD_INITIAL, tokens[0]):
        return None
    if not re.fullmatch(_WORD_FULL, tokens[-1]):
        return None
    return " ".join(tokens)


# Back-compat: il nome storico era `_trim_blacklisted_first_tokens` (solo head).
_trim_blacklisted_first_tokens = _trim_blacklisted_edge_tokens


def extract_popes(text: str) -> list[Candidate]:
    if not text:
        return []
    text = text + " "
    return _dedupe_per_match(
        [Candidate(surface_form=m.group(0).strip(), ner_type="REGEX_POPE")
         for m in _RE_POPE.finditer(text)]
    )


def extract_brand_alphanum(text: str) -> list[Candidate]:
    if not text:
        return []
    text = text + " "
    out: list[Candidate] = []
    for m in _RE_BRAND_ALPHA.finditer(text):
        surface = m.group(1)
        if surface.upper() in _SIGLA_BLACKLIST:
            continue
        out.append(Candidate(surface_form=surface, ner_type="REGEX_BRAND_ALPHA"))
    return _dedupe_per_match(out)


def extract_brand_single(text: str) -> list[Candidate]:
    """Parola singola capitalizzata (4+ char) in mid-sentence."""
    if not text:
        return []
    text = text + " "
    out: list[Candidate] = []
    for m in _RE_BRAND_SINGLE.finditer(text):
        surface = m.group(1)
        if surface in _BRAND_SINGLE_BLACKLIST:
            continue
        out.append(Candidate(surface_form=surface, ner_type="REGEX_BRAND_SINGLE"))
    return _dedupe_per_match(out)


def extract_models(text: str, *, known_brands: Iterable[str]) -> list[Candidate]:
    """Estrae model = `<known_brand> <num|word> [num|word]`.

    `known_brands` è una lista di stringhe già confermate come `brand`
    (esempio: ["Porsche", "Boeing", "Alfa Romeo"]). Il match richiede che
    la prima parola/coppia sia esattamente uno di questi brand.
    """
    if not text:
        return []
    text = text + " "  # garantisce boundary per model a fine stringa
    brands = [b for b in {b.strip() for b in known_brands} if b]
    if not brands:
        return []
    # Ordina per lunghezza desc così "Alfa Romeo" prima di "Alfa".
    brands.sort(key=len, reverse=True)
    escaped = "|".join(re.escape(b) for b in brands)
    # Token "MODEL_PART" copre nomi prodotto reali:
    #   - 911, 747, 33                             (numeri puri)
    #   - Panda, Stradale, Serie, Pro, Ultra, Max  (parola full)
    #   - WH-1000XM5, L27-41, RTX-4090, A12X       (alfanumerico con dash interno)
    #   - 4K, 8K, 12C, 33-Stradale                 (digit-led con suffisso)
    #   - iPhone, iPad, MacBook, ThinkPad          (camelCase con minuscola iniziale)
    # NOTA: il pattern alfanumerico richiede ALMENO un digit per evitare match
    # su sigle pure (RAI, BMW, ...) — quelle vivono in REGEX_BRAND_ALPHA.
    # Eccezioni: nomi prodotto camelCase con minuscola iniziale (non gestibili
    # con un pattern generico senza esplosione di falsi positivi). Whitelist
    # chiusa, da estendere quando emerge un nuovo brand con questa convenzione.
    product_exceptions = (
        "iPhone", "iPad", "iMac", "iPod", "iCloud", "iOS", "iPadOS",
        "iQOO", "iQoo",      # Vivo gaming sub-brand
        "reMarkable",        # tablet e-paper (proprio brand)
    )
    exceptions_alt = "|".join(re.escape(p) for p in product_exceptions)
    model_part = (
        rf"(?:"
        rf"{exceptions_alt}"                                  # iPhone, iPad, iMac, ...
        rf"|\d{{1,4}}"                                        # 4, 33, 911, 1000
        rf"|[{_LETTER_UP}][{_LETTER_LO}]+"
        rf"|[{_LETTER_UP}][\w-]*\d[\w-]*"                     # WH-1000XM5, L27-41
        rf"|\d+[{_LETTER_UP}][\w-]*"                          # 4K, 8K, 12C
        rf"|[{_LETTER_UP}][{_LETTER_LO}]*-[{_LETTER_UP}][{_LETTER_LO}]+"  # P-Wind, X-Pro
        rf")"
    )
    # Brand match case-insensitive (gestisce "HUAWEI" all-caps in titoli urlati,
    # "Apple" Title Case, "huawei" lowercase). Il resto del pattern (model_part)
    # resta case-sensitive: i nomi prodotto reali sono sempre Title Case o
    # all-caps con digit. Fino a 4 token post-brand per accomodare nomi lunghi
    # tipo "Huawei Watch Fit 5 Series".
    pattern = re.compile(
        rf"""
        \b ((?i:{escaped})) \s+
        ({model_part})
        (?: \s+ ({model_part}) )?
        (?: \s+ ({model_part}) )?
        (?: \s+ ({model_part}) )?
        \b
        """,
        re.VERBOSE,
    )
    out: list[Candidate] = []
    for m in pattern.finditer(text):
        surface = m.group(0).strip()
        # Trim degli edge token blacklisted (articoli IT, parole comuni
        # capitalizzate). Es: "Leapmotor Il" → "Leapmotor" → scartato
        # perché resta solo il brand senza model_part (< 2 token).
        trimmed = _trim_blacklisted_edge_tokens(surface)
        if trimmed is None:
            continue
        out.append(Candidate(surface_form=trimmed, ner_type="REGEX_MODEL"))
    return _dedupe_per_match(out)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _person_has_blacklisted_sigla(surface: str) -> bool:
    """Se nei token c'è una sigla in blacklist, scarta il match."""
    for token in surface.split():
        clean = token.rstrip(".")
        if clean.isupper() and clean in _SIGLA_BLACKLIST:
            return True
    return False


def _dedupe_per_match(items: list[Candidate]) -> list[Candidate]:
    """Stessa surface_form (case-sensitive) appare al massimo 1 volta nello
    stesso testo. La frequenza per articolo viene gestita dall'aggregator
    (counts su entity_source_counts)."""
    seen: set[tuple[str, str]] = set()
    out: list[Candidate] = []
    for c in items:
        key = (c.surface_form, c.ner_type)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def extract_all(
    text: str, *, known_brands: Iterable[str] | None = None
) -> list[Candidate]:
    """Esegue tutti gli extractor base + (se `known_brands` fornito) MODEL."""
    out: list[Candidate] = []
    out.extend(extract_persons(text))
    out.extend(extract_popes(text))
    out.extend(extract_brand_alphanum(text))
    out.extend(extract_brand_single(text))
    if known_brands:
        out.extend(extract_models(text, known_brands=known_brands))
    return out
