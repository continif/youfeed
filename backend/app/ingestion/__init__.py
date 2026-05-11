"""Pipeline di ingestion: discovery URL + fetch RSS/WP + normalize + classify.

Vedi `Claude/INGESTION.md` per il design completo.
  - discovery.py        — qualificazione URL -> kind RSS/WP/invalid
  - feed_parser.py      — fetch RSS/Atom -> ArticleCandidate (puro)
  - wp_api.py           — fetch WordPress REST -> ArticleCandidate (puro)
  - normalize.py        — HTML clean + content extract + image fallback
  - classify.py         — dictionary matching su Topic.aliases
  - manticore_client.py — HTTP JSON client per articles_rt
"""
