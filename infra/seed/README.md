# Seed YOUFEED

File di seed per il database iniziale. Caricati da `app.utils.seed_loader`
durante il bootstrap (vedi script `infra/scripts/seed.py` quando arriverà).

## File

| File | Tabella destinazione | Note |
|---|---|---|
| `categories_suggested.yaml` | nessuna (consumato dal frontend) | Mostrato nell'`<OnboardingTour>` step 2 |
| `featured_sources.yaml` | `featured_sources` (+ `sources` se assenti) | URL feed/wp_api_root da revalidare con discovery |
| `topics.yaml` | `topics` | Lista starter ~70 entry — espandere a 200-500 prima del lancio v1.0 |

## Schema

### `topics.yaml`

```yaml
- slug: inter                    # univoco URL-safe
  type: brand                    # brand | person | subject
  display_name: Inter            # forma canonica
  aliases:                       # forme alternative case-insensitive
    - "FC Internazionale"
    - "i nerazzurri"
  description: "..."             # opzionale, sovrascritto da Wikidata in v1.2
  wikidata: Q631                 # opzionale, popola external_refs.wikidata
```

### `featured_sources.yaml`

```yaml
- slug: repubblica
  display_name: la Repubblica
  description: "..."
  url_site: https://www.repubblica.it
  url_feed: https://www.repubblica.it/rss/...    # se RSS
  # in alternativa:
  # wp_api_root: https://www.example.it/wp-json/wp/v2
  category_hint: cronaca         # match con categories_suggested.yaml
  position: 10                   # ordine nella gallery
```

### `categories_suggested.yaml`

```yaml
- slug: politica
  name: Politica
  description: "..."
  default_color: "#dc2626"
```

## Caricamento

```bash
# Una tantum, dopo le migration:
backend/.venv/bin/python -m app.utils.seed_loader \
  --topics ../infra/seed/topics.yaml \
  --featured ../infra/seed/featured_sources.yaml
```

(Lo script `seed_loader` arriverà in Phase 2.)

## Espansione

I tre file sono pensati come starter — ogni file ha sezioni `TODO` con
suggerimenti per arrivare ai volumi target di v1.0. Aggiungere senza
preoccuparsi di duplicati: il loader fa upsert per slug.
