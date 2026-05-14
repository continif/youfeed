# YouFeed Admin (`/yf_admin/*`)

Pannello server-rendered Jinja2 — niente SPA, niente build step. Auth tramite
HTTP Basic con `ADMIN_USERNAME` + `ADMIN_PASSWORD` da `.env`. Il prefisso
`/yf_admin/` è isolato da Apache vhost (no proxy verso Vite) e va
dietro reverse proxy HTTPS.

Scopo: governare il traffico di contenuti che attraversa la pipeline
(sources → articles → topics) senza dover toccare il DB a mano.

## Layout di base

- **Codice**: [backend/app/routers/admin.py](../backend/app/routers/admin.py)
- **Template**: [backend/app/templates/admin/](../backend/app/templates/admin/)
- **CSS**: [backend/app/static/css/admin.css](../backend/app/static/css/admin.css)
- **Auth helper**: [backend/app/admin_deps.py](../backend/app/admin_deps.py)

Template Jinja `base.html` con header + footer comune. Niente JS pesante:
solo `<form>` POST classici e pochi inline `onsubmit` per le conferme.

## Sezioni del menù

Il top-bar di `admin/base.html` è organizzato per area funzionale:

```
Utenti  ·  Topic ▾  ·  Sources  ·  Featured  ·  Stats  ·  [→ ID articolo]
            ├─ Lista topic           (/yf_admin/topics)
            ├─ Entità non risolte    (/yf_admin/entities)
            ├─ Ambigui               (/yf_admin/rules/ambigui)
            ├─ Blacklist             (/yf_admin/rules/blacklist)
            ├─ Case-sensitive        (/yf_admin/rules/case-sensitive)
            └─ Composite             (/yf_admin/composite)
```

Tutto ciò che riguarda il *grafo dei topic* (curated, auto-extracted,
entità grezze NER, regole di matching) sta sotto `Topic ▾`.

## Routes principali

### Utenti — `/yf_admin/users`
- Lista paginata con search per username/email
- Vista di profili (ruolo, email_verified, onboarding, ultimo login)

### Topic — `/yf_admin/topics`
- Lista con filtri (`q`, `type`, `is_curated`)
- `POST /topics/create` — crea topic curated da zero
- `POST /topics/bulk` — azioni di massa (delete, merge, ricalcolo)
- `GET/POST /topics/{id}` — edit (display_name, type, aliases, descrizione, curated)
- `POST /topics/{id}/delete` — elimina (CASCADE su `article_topics`)
- Edit invalida la cache di [classify](../backend/app/ingestion/classify.py)

### Entità non risolte — `/yf_admin/entities`
Entità NER/regex emerse dall'ingestion ma non ancora associate a un topic.

- Filtra per `ner_type` e `min_count`
- **Promuovi** → crea topic curated (con auto-enrichment Wikidata)
- **Collega** → riusa topic esistente (passa `topic_id`)
- **Ignora** → marca come `skip` (non riappare)

### Rules — `/yf_admin/rules/{slug}`
Slug ammessi: `ambigui` (Topic ambigui da risolvere via contesto),
`blacklist` (termini da non matchare mai), `case-sensitive` (match solo
con esatta capitalizzazione).

- `POST /rules` con `kind` per creare
- `POST /rules/{id}/delete` per rimuovere

### Composite — `/yf_admin/composite`
Regole che associano più slug a un singolo topic (sinonimi/aggregazioni:
es. `chatgpt`, `gpt-4`, `gpt-5` → topic `openai-models`).

### Sources — `/yf_admin/sources`
Lista feed RSS censiti, con health (`consecutive_failures`,
`last_polled_at`). `POST /sources/{id}/reset-failures` per riarmare un feed
che ha smesso di rispondere.

### Featured — `/yf_admin/featured`
Sources promosse in homepage / onboarding (gli utenti le vedono come
suggerimenti). CRUD minimo.

### Stats — `/yf_admin/stats`
Conteggi globali (utenti, topic, articoli) + top topic per occorrenze.

### Articoli — `/yf_admin/articles/{id}`
Inspector che mostra raw_meta, topic associati con score, log di classify.
Search rapida dal form in topbar (input `article_id`).

### Cache reload — `POST /yf_admin/cache/reload`
Invalida la cache in-memory di classify (utile dopo edit massivo di rules).

## Workflow tipico

1. **Triage Entità non risolte** (settimanale): scorri le top N per
   `occurrence_count`, promuovi quelle ricorrenti, ignora il rumore NER.
2. **Topic enrichment**: dopo promote, gira
   `python -m app.utils.refresh_topics --reenrich --limit 100`
   per popolare i campi nuovi da Wikidata (vedi [INGESTION.md](INGESTION.md)).
3. **Reclassify type**: occasionalmente
   `python -m app.utils.refresh_topics --reclassify-type --all --apply`
   per portare i type esistenti dietro a P31 (es. `brand` → `company`).
4. **Rules tuning**: se un topic matcha troppo o troppo poco, aggiungi
   `case-sensitive` / `blacklist` / `ambigui`. Poi `POST /cache/reload`.

## Sicurezza

- HTTP Basic davanti a TUTTE le route (anche GET dashboard). Niente bypass.
- Le password admin stanno in `.env`, mai committate.
- L'header `noindex,nofollow` blocca crawler accidentali.
- Nessuna CSRF protection sui POST: il pannello assume operatore di
  fiducia dietro VPN/Cloudflare; non esporre in chiaro su internet.

## TODO / Idee future

- Activity log delle azioni admin (chi ha cancellato cosa)
- Bulk delete di Entità (oggi solo singole)
- Vista "feed health" aggregata (sources con failure rate > soglia)
- Export CSV di topic/sources per audit
