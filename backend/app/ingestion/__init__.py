"""Pipeline di ingestion: discovery URL + fetch RSS/WP + normalize + classify.

Vedi `Claude/INGESTION.md` per il design completo. Phase di sviluppo:
  - Phase 8 (questa): `discovery.py` — qualificazione URL → kind RSS/WP/invalid
  - Phase 9: fetch + parse + normalize + dedup → DB
  - Phase 10: image processing (resize WebP)
"""
