"""User-Agent centralizzato per le richieste outbound della ingestion.

Convenzione adottata:
- Il TOKEN (`YouFeed`) è la stringa che i webmaster useranno in robots.txt
  e nelle regole WAF per identificarci selettivamente
  (es. `User-agent: YouFeed` / `Disallow: /private/`).
- La stringa COMPLETA contiene token + versione + URL pagina-bot, secondo
  best practice (vedi Googlebot, Bingbot, ApplebotMobileWeb).

Quando bumpiamo il major (es. cambia architettura ingestion, cambia
profilo di traffico), aggiorniamo la VERSION. Non ribattezzare il TOKEN
senza un buon motivo: i webmaster hanno già regole che lo prevedono.
"""

from __future__ import annotations


USER_AGENT_TOKEN = "YouFeed"
USER_AGENT_VERSION = "2.0"
USER_AGENT = (
    f"{USER_AGENT_TOKEN}/{USER_AGENT_VERSION} (+https://www.youfeed.it/bot)"
)
