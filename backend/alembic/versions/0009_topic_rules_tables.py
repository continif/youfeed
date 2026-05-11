"""Crea tabelle topic_term_rules e topic_composite_rules + seed iniziale.

Sposta in DB le frozenset hardcoded in `classify.py` e `extractor.py`:
  - _AMBIGUOUS_LOCATION_TERMS (kind='ambiguous_location')
  - _BRAND_SINGLE_BLACKLIST (kind='brand_single')
  - _CASE_SENSITIVE_SLUGS (kind='case_sensitive_slug')

Più _COMPOSITE_RULES come tabella separata (component slugs in TEXT[]).

Dopo questa migration le regole sono editabili dall'admin senza redeploy.

Revision ID: 0009_topic_rules_tables
Revises: 0008_at_composite_source
Create Date: 2026-05-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0009_topic_rules_tables"
down_revision: str | Sequence[str] | None = "0008_at_composite_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Seed iniziale (snapshot del 2026-05-08 dei frozenset hardcoded).
# Manteniamo l'origine come `note` per tracciare la storia.
_AMBIGUOUS_LOCATION = [
    "bomba", "campagna", "canale", "dello", "fascia", "grosso",
    "lago", "lana", "massa", "nave", "norma", "ora", "prato",
    "rende", "sale", "scala", "scena", "terrazzo", "ultimo", "vita",
    "fonte", "fonti", "sostegno", "la cassa",
    "ne", "mira", "alto", "posta",
    "acuto", "casella", "front", "licenza", "matrice", "mese", "quindici",
    "chiari", "fondi", "premia",
    "paese", "siano",
]

_BRAND_SINGLE = [
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
    "Crescono", "Vincono", "Perdono", "Salgono", "Scendono",
    "Sembrano", "Restano", "Diventano", "Crollano", "Scoppiano",
    "Vogliono", "Devono", "Possono", "Sanno", "Dicono", "Pensano",
    "Aprono", "Chiudono", "Guidano", "Trovano", "Decidono",
    "Annunciano", "Confermano", "Smentiscono", "Replicano",
    "Accordo", "Accordi", "Norma", "Norme", "Corte", "Corti",
    "Reddito", "Redditi", "Giro", "Giri", "Patto", "Patti",
    "Trattato", "Trattati", "Decreto", "Decreti", "Legge", "Leggi",
    "Riforma", "Riforme", "Direttiva", "Direttive", "Alba", "Albe",
    "Watch", "Mini", "Pro", "Plus", "Max", "Ultra", "Lite", "Series",
    "Gaming", "Demand", "Edition", "Premium", "Standard",
    "Italia", "Europa",
    "Regno", "Unito",
    "Fonte", "Fonti", "Sostegno", "Cassa",
    "Stati", "Paesi",
    "Formula", "Champions", "Coppa", "Mondiale", "Mondiali",
    "Bomba", "Bombe", "Boom", "Bombetta",
    "Fascia", "Canale", "Campagna", "Strada", "Storia", "Famiglia",
    "Festa", "Fortuna", "Sorpresa", "Scoperta", "Indagine",
    "Polemica", "Scandalo", "Sciopero", "Manovra", "Ripresa", "Crescita",
    "Calo", "Crollo", "Allarme", "Ondata", "Stretta", "Svolta", "Corsa",
    "Attacco", "Difesa", "Vittoria", "Sconfitta", "Pareggio",
    "Squadra", "Campionato", "Finale", "Maglia", "Stadio",
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
    "Nuovo", "Nuova", "Nuovi", "Nuove", "Vecchio", "Vecchia",
    "Grande", "Grandi", "Piccolo", "Piccola",
    "Buona", "Cattivo", "Cattiva",
    "Bello", "Bella", "Belli", "Belle", "Brutto", "Brutta",
    "Ottimo", "Ottima", "Pessimo", "Pessima", "Migliore", "Peggiore",
    "Massimo", "Massima", "Minimo", "Minima",
    "Primo", "Secondo", "Seconda", "Terzo", "Terza",
    "Ultimo", "Ultima", "Penultimo",
    "Dello", "Della", "Delle", "Degli", "Sullo", "Sulla", "Sulle",
    "Sugli", "Nello", "Nella", "Nelle", "Negli", "Quello", "Quella",
    "Quelli", "Quelle", "Questo", "Questa", "Questi", "Queste",
    "Stesso", "Stessa", "Stessi", "Stesse",
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
    "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato",
    "Domenica",
    "Uniti", "Home", "Punti", "Iscriviti", "Invia",
    "Paese", "Siano", "Data", "State",
]

_CASE_SENSITIVE = [
    "lancia", "lanciano", "vespa", "panda", "bologna", "rai", "tim", "lega",
    "alba", "noto", "capaci",
    "forza-italia", "pd", "m5s", "fratelli-d-italia",
    "alleanza-verdi-sinistra", "italia-viva", "azione",
    "oled", "led", "microled", "mini-led", "lcd", "4k", "8k",
    "onu", "europa", "bce", "nato", "ocse",
]

_COMPOSITE = [
    ("google-gemini", ["google", "gemini"]),
]


def upgrade() -> None:
    op.create_table(
        "topic_term_rules",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("kind", "term", name="uq_topic_term_rules_kind_term"),
        sa.CheckConstraint(
            "kind IN ('ambiguous_location', 'brand_single', 'case_sensitive_slug')",
            name="ck_topic_term_rules_kind",
        ),
    )
    op.create_index(
        "ix_topic_term_rules_kind", "topic_term_rules", ["kind"]
    )

    op.create_table(
        "topic_composite_rules",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("composite_slug", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "components",
            sa.dialects.postgresql.ARRAY(sa.Text()),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Seed
    bind = op.get_bind()
    rows_terms: list[dict[str, str]] = []
    for term in _AMBIGUOUS_LOCATION:
        rows_terms.append({"kind": "ambiguous_location", "term": term})
    for term in _BRAND_SINGLE:
        rows_terms.append({"kind": "brand_single", "term": term})
    for slug in _CASE_SENSITIVE:
        rows_terms.append({"kind": "case_sensitive_slug", "term": slug})
    if rows_terms:
        bind.execute(
            sa.text(
                "INSERT INTO topic_term_rules (kind, term) "
                "VALUES (:kind, :term) ON CONFLICT DO NOTHING"
            ),
            rows_terms,
        )
    for composite_slug, components in _COMPOSITE:
        bind.execute(
            sa.text(
                "INSERT INTO topic_composite_rules (composite_slug, components) "
                "VALUES (:slug, :components) ON CONFLICT DO NOTHING"
            ),
            {"slug": composite_slug, "components": components},
        )


def downgrade() -> None:
    op.drop_index("ix_topic_term_rules_kind", table_name="topic_term_rules")
    op.drop_table("topic_composite_rules")
    op.drop_table("topic_term_rules")
