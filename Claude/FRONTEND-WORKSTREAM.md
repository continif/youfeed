# FRONTEND — workstream UX timeline (loggato)

Stream parallelo a Phase 21 v1.0. Aggrega le richieste mirate di UX/UI sul
flusso loggato (sidebar, card, vista articolo, correlati).

NON copre: home pubblica, profilo pubblico `/{username}`, SPA auth pages
(quelle restano nel master plan).

## Convenzioni
- ID task: `F-001`, `F-002`, ... ordine di apertura, mai riusati.
- Stato: `[ ]` aperto · `[~]` in corso · `[✓]` chiuso · `[⚠]` bloccato
- Ogni task ha: descrizione, area/file, scelte di design, DoD.

## Backlog

### F-001 — Sidebar categorie utente + filtro timeline (solo loggato)
- **Stato**: [✓] (2026-05-08)
- **Backend**
  - `articles_service.timeline_for_user(category_id: int | None)` filtra
    user_sources con `category_id IN (root, *descendants)`.
  - Helper `_descendant_category_ids(session, user_id, root_id)`: BFS
    sull'albero (max 2 livelli in v1.0, semplice).
  - `routers/articles.py` `GET /yf_articles/feed?category=<id>`.
- **Frontend**
  - `AppLayout.vue`: nuova sezione sidebar "Le mie categorie" che renderizza
    l'albero in modalità sola lettura. Click → `router.push('/me/feed?category=<id>')`.
  - `Feed.vue`: passa `category` al fetcher; reload via watcher su route.
  - `services/articles.ts`: param `category` nel fetch.
- **DoD**: click su categoria root → solo articoli da source di quella + sotto;
  click su sotto-categoria → solo quella; nessun filtro = feed completo.

### F-002 — Bordi card colorati per categoria (loggato + profilo pubblico)
- **Stato**: [✓] (2026-05-08)
- **Backend**
  - `ArticleListItem` payload aggiunge `category_color: string | null`.
  - `to_list_item` lookup `user_source.category.default_color` per la source
    nel contesto utente (per `timeline_for_user`) o utente target (per
    `timeline_for_public_user`). Pre-fetch in batch
    `(user_id, source_id) → color` per evitare N+1.
- **Frontend**
  - `ArticleCard.vue`: `:style="{borderColor: item.category_color, borderWidth: '2px'}"`.
  - `profile.html` Jinja: `style="border:2px solid {{ item.category_color }}"`.
  - Fallback grigio (var CSS) quando `null`.
- **DoD**: card timeline e profilo pubblico mostrano bordo 2px del colore
  categoria di appartenenza.

### F-003 — Colore sfondo personalizzato (localStorage)
- **Stato**: [✓] (2026-05-08)
- **Frontend only**
  - Composable `useBackgroundColor.ts`: stato reactive da
    `localStorage.yf_bg_color`. `setColor(hex|null)`, `reset()`.
  - Settings page (in `PrivacySettings.vue` o nuova `AspectSettings.vue`):
    color picker hex + bottone reset.
  - `App.vue`: watcher applica `document.body.style.backgroundColor = color`
    (sovrascrive var tema). Reset → clear inline style.
- **DoD**: utente sceglie colore, refresh → persiste; reset → torna a default
  tema dark/light.

### F-004 — Hover shadow theme-aware
- **Stato**: [✓] (2026-05-08)
- **Frontend only, pure CSS**
  - SPA `ArticleCard.vue`: classi Tailwind
    `hover:shadow-lg dark:hover:shadow-white/10`.
  - Public `public.css`:
    ```css
    .yf-card { transition: box-shadow .15s ease; }
    .yf-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,.18); }
    [data-theme="dark"] .yf-card:hover { box-shadow: 0 4px 16px rgba(255,255,255,.12); }
    ```
- **DoD**: hover su card produce ombra coerente col tema, semitrasparente.

### F-005 — Vista articolo espanso + notizie correlate
- **Stato**: [✓] (2026-05-08)
- **Decisione algoritmo**: implementare **3 formule** di overlap selezionabili
  via query param `?formula={max|source|jaccard}` per A/B test, default `max`:
  - `max`: `|A∩B| / max(|A|,|B|)` — bilanciato
  - `source`: `|A∩B| / |A|` — sbilanciato verso copertura del sorgente
  - `jaccard`: `|A∩B| / |A∪B|` — più severo
- **Backend**
  - `articles_service.related_articles(session, *, article_id, days_window=15,
    min_overlap=0.6, formula='max', limit=20)`:
    1. fetch topic_ids dell'articolo sorgente.
    2. window: `published_at BETWEEN src - 15d AND src + 15d` AND
       `id != src.id` AND `processing_status='indexed'`.
    3. CTE: per ogni candidato calcola `inter`, `b_size`. Filtra
       `inter / formula(...) >= min_overlap`.
    4. Ordina per overlap desc, poi |published_at - src.published_at| asc.
  - Endpoint `GET /yf_articles/{id}/related?days=15&min_overlap=0.6&formula=max`.
- **Frontend SPA**
  - Route `/me/article/:id` (URL stabile). Componente `ArticleDetail.vue`.
  - Layout: desktop split-view (60/40 article + sidebar correlati);
    mobile stack (article + sotto correlati).
  - `<RelatedArticles>` riusa `<ArticleCard>` in modalità compatta.
  - Toggle UI per cambiare formula (debug A/B).
  - Click su card timeline → `router.push('/me/article/:id')` (no più
    `target=_blank`). CTA dentro detail apre `url_canonical` esterno.
- **Frontend pubblico (Jinja)**: postponed — solo SPA loggato in MVP.
- **DoD**: click su card del feed → pagina dedicata con article completo +
  blocco correlati. Le 3 formule sono testabili col toggle. Soglia 60% rispettata.

## Ordine consigliato (chiusura)
1. F-002 + F-003 + F-004 insieme (CSS/UI + minimo backend).
2. F-001 (backend+sidebar).
3. F-005 (più ampio).

## Stato 2026-05-08
Tutti e 5 i task chiusi. Smoke verificato:
- Sidebar mostra le categorie sopra il menù principale (separate da `<hr>`).
- Filtro per categoria funziona (incl. sotto-categorie).
- Bordi card colorati col `category.color`, hover shadow theme-aware,
  sfondo personalizzabile da `/me/settings/aspect`.
- Vista articolo `/me/article/:id` con correlati nella sidebar (desktop) o
  sotto (mobile). Toggle formula `max | source | jaccard` per A/B test.
  Esempio reale (Qualcomm Snapdragon 4): correlato trovato a 0.75 max,
  0.75 source, 0.60 jaccard.

Decisioni chiuse:
- **Algoritmo correlati default**: `max` — bilanciato tra copertura
  e specificità. `source` privilegia copertura (utile se l'articolo sorgente
  è la "perla rara"). `jaccard` è il più severo (limita a corpus simili).
  Lascio il toggle UI per debug, ma nessuna persistenza preferenza.
- **URL stabile** `/me/article/:id` (non drawer): consente share + cache
  del browser back-forward. Click su `<ArticleCard>` ora navigate-internal
  via `<RouterLink>`; il bottone "Apri originale ↗" della detail apre
  l'`url_canonical` esterno in nuova tab.
