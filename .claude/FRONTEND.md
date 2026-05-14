# Frontend

## Architettura: due frontend

YOUFEED ha due "facce" con esigenze opposte. Le serviamo con due tecnologie diverse, con Tailwind in comune per coerenza visiva.

| | Pagine pubbliche | App utente loggato |
|---|---|---|
| **Esigenza primaria** | SEO, condivisibilità, anteprime social, performance estrema | Interattività, gestione stato, ottimismo UI, real-time |
| **Tecnologia** | **Jinja2 lato FastAPI** (server-rendered HTML) | **Vue 3 SPA** |
| **Cache** | Cloudflare aggressiva (TTL alto, purge selettivo) | Nessuna cache (tutto dinamico per utente) |
| **Stato JS** | Minimo (progressive enhancement) | Pinia, Vue Router, axios |

Le due facce condividono cookie session, design system Tailwind, asset (loghi, font, icone) e API. Il browser cambia "modalità" semplicemente cliccando da una pagina all'altra — niente SSR/hydration, niente Nuxt.

### Pagine pubbliche (Jinja2)

Tutte renderizzate dal dispatcher catch-all FastAPI `GET /{username}/{rest:path}` + alcuni endpoint statici globali:

- `/` — home pubblica raggruppata per topic
- `/about`, `/privacy`, `/terms` — pagine statiche
- `/{username}` — profilo pubblico + ultime news
- `/{username}/{category}` / `/{category}/{sub}` — news di categoria
- `/{username}/topic/{name}` — news per topic
- Le varianti `.../rss` ritornano `application/rss+xml` con un template separato

Ogni template HTML genera meta tag completi (`<title>`, `description`, Open Graph, Twitter Card, JSON-LD `WebSite`/`CollectionPage`/`NewsArticle`) + sitemap-friendly canonical URLs. Cloudflare cache con `Cache-Control: public, s-maxage=300` e purge mirato all'ingestion di nuovi articoli.

### App utente (Vue SPA)

Tutto sotto i path "applicativi" gestiti da Vue Router:
- `/login`, `/register`, `/verify-email`, `/forgot-password`, `/reset-password`, `/oauth-callback`
- `/me/*` (timeline, categorie, fonti, settings, alert, notifiche)
- `/search` (v1.1)

Apache instrada questi path su `index.html` della build Vue; Vue Router fa il resto lato client. Tutti questi percorsi sono in [reserved-words.txt](reserved-words.txt) → nessun utente può registrarsi con uno di essi come username.

## Apache routing

```
/yf_*                       → FastAPI API (JSON)
/static/*, /assets/*        → Vue build
/sw.js, /manifest.json,
  /favicon.ico, /robots.txt → file statici
/sitemap.xml                → FastAPI (dinamica)

/login, /register,
/verify-email, /forgot-password,
/reset-password, /oauth-callback,
/me, /me/*, /search         → Vue SPA index.html (rewrite)

/, /about, /privacy, /terms,
/{username}, /{username}/* → FastAPI HTML (Jinja2)
```

---

## Stack Vue SPA

- **Framework**: Vue 3 (Composition API) + `<script setup>`
- **Build**: Vite
- **Linguaggio**: TypeScript
- **Routing**: Vue Router
- **State**: Pinia
- **HTTP**: `ky` (axios più piccolo) o `axios`. Service-layer su `useFetch` composable
- **Form / validazione**: VeeValidate + Zod (schema condivisi tra form e parsing risposte API)
- **Stile**: **Tailwind CSS** (in comune con Jinja), `darkMode: 'class'`
- **Theme switcher**: VueUse `useDark()` + `useToggle()`, persistito in `localStorage` chiave `yf_theme`
- **Componenti accessibili**: **Headless UI** + componenti custom in `src/components/ui/`
- **Icone**: Heroicons (set Tailwind ufficiale)
- **Date**: `date-fns` con locale `it`
- **Drag & drop** (alberatura categorie): `vue-draggable-plus`
- **Masonry layout**: CSS columns nativo (`columns-2 md:columns-3 lg:columns-4 gap-4` + `break-inside-avoid` sulle card). Niente libreria, niente JS — `image_width`/`image_height` su `articles` permettono di riservare lo spazio prima del load.
- **First-login tour**: `Driver.js` (vanilla, ~5 KB gzipped, controllabile da Vue)
- **Fingerprint**: `@fingerprintjs/fingerprintjs` (open source) — caricato **dopo** consenso cookie
- **Web push**: Service Worker custom + `Notification API` (v1.2)
- **Test**: Vitest (unit), Playwright (e2e), Vue Testing Library
- **i18n**: nessuno (app IT-only)

---

## Routing SPA

```
/login                              LoginPage
/register                           RegisterPage
/verify-email-pending               VerifyEmailPendingPage
/verify-email                       VerifyEmailTokenPage          ?token=...
/forgot-password                    ForgotPasswordPage            (v1.1)
/reset-password                     ResetPasswordPage             ?token=... (v1.1)
/oauth-callback                     OAuthCallbackPage             (v1.1)

/me                                 → redirect /me/timeline
/me/timeline                        TimelinePage                  default category=all
/me/timeline/category/:slug+        TimelinePage                  con filtro categoria
/me/timeline/topic/:slug            TimelinePage                  con filtro topic
/me/sources                         SourcesPage
/me/sources/add                     AddSourcePage                 wizard discover
/me/categories                      CategoriesPage                editor alberatura
/me/settings                        → redirect /me/settings/account
/me/settings/account                AccountSettingsPage           (cambio password, GDPR export/delete)
/me/settings/privacy                PrivacySettingsPage           (cookie/tracking)
/me/settings/devices                DevicesPage                   (v1.1)
/me/settings/notifications          NotificationsSettingsPage     (push, v1.2)
/me/notifications                   NotificationsPage             (v1.1)
/me/alerts                          AlertsPage                    (v1.2)
/me/alerts/new                      AlertEditorPage               (v1.2)
/me/alerts/:id                      AlertEditorPage               (v1.2)

/search                             SearchPage                    (v1.1)  ?q=...
```

Catch-all `:slug+` per la route categoria abilita path nidificati `/me/timeline/category/sport/serie-a`.

### Guards

- Tutti i path sotto `/me/*` richiedono `useAuthStore().isAuthenticated` — se assente, redirect a `/login?redirect=...`
- `/login` e `/register` redirettano a `/me/timeline` se già loggati
- I path `/verify-email`, `/reset-password`, `/oauth-callback` sono accessibili in entrambi gli stati

---

## State management (Pinia)

```
stores/
  auth.ts          isAuthenticated, user, fingerprint, login(), logout(), refresh()
  categories.ts    tree, fetch(), create(), update(), move(), delete()
  sources.ts       list, fetch(), discover(url), add(), patch(), delete()
  timeline.ts      items[], cursor, loading, fetch(filter), loadMore()
  topics.ts        catalog (lazy fetch), getBySlug()
  notifications.ts list, unreadCount, markRead(id)                          (v1.1)
  search.ts        query, results, suggest()                                (v1.1)
  alerts.ts        list, create(), update(), delete()                       (v1.2)
  push.ts          subscription, vapidKey, subscribe(), unsubscribe()       (v1.2)
  consent.ts       cookie/tracking consent state
  devices.ts       sessions, revoke(id)                                      (v1.1)
```

**Pattern condivisi**:
- Stato `loading` / `error` per ogni store con azione async
- Aggiornamenti ottimistici su categorie (riordino, rinomina) e mark-read notifications
- Invalidation manuale dopo mutazioni (no fetch automatico tipo react-query nel MVP)
- Persistenza locale: `auth.user` (per evitare flash al refresh), `consent` (per non chiedere ogni reload)

---

## Service-layer API

```
src/services/
  api.ts             ky instance con baseURL = '/yf_', timeout, JSON, credentials: 'include'
  interceptors.ts    inject X-YF-Fingerprint header, gestione 401 → logout, gestione 429 → backoff
  authService.ts     register, login, logout, verifyEmail, ...
  meService.ts       me, changePassword, exportData, deleteAccount, devices
  categoriesService.ts
  sourcesService.ts
  alertsService.ts   (v1.2)
  pushService.ts     (v1.2)
  searchService.ts   (v1.1)
  trackService.ts    POST /yf_track in batch (debounced)
```

Schemi Zod condivisi in `src/types/api.ts` per validare le risposte (defensive: non ci fidiamo dei tipi senza validazione runtime al boundary).

---

## Componenti chiave

### `<ArticleCard>`
Variante **masonry** (default per timeline e topic page), variante **search result** (orizzontale con highlight). Mostra: thumbnail responsive (vedi sotto), titolo, fonte+favicon, published_at relativo (`due ore fa`), chip topic, indicatore "letto", **bordo sinistro 4px nel colore della categoria di appartenenza** (riconoscimento visivo immediato).

Layout immagine con `<picture>` + `srcset` per servire la variante giusta:
```html
<picture>
  <source media="(max-width: 768px)" srcset="/images/{path}_m.webp">
  <img src="/images/{path}_d.webp"
       width="{image_width}" height="{image_height}"
       loading="lazy" alt="">
</picture>
```
Se `image_status='failed'` o `'skipped'`, fallback su `image_url` originale. `width`/`height` originali sull'`<img>` riservano lo spazio prima del load → niente CLS, masonry stabile.

Click registra `impression`/`click` via `trackService`.

### `<CategoryTree>`
Editor drag-and-drop dell'alberatura. Nodi nidificati, espandi/comprimi, slug auto-generato dal nome (modificabile). Validazione client (no slug duplicati per parent), debounce 500ms su patch al backend. Versione read-only riusata nella sidebar timeline.

Ogni nodo ha un **`<CategoryColorPicker>`** integrato:
- 16 swatch preset (palette Tailwind a saturazione media)
- Input hex custom
- Quando l'utente sceglie un hex custom, mostriamo accanto **4 colori derivati dalla ruota dei colori** (complementare a 180°, analogo +30°, analogo -30°, triadico +120°) cliccabili — l'utente trova subito accordi cromatici sensati senza dover sapere niente di teoria del colore
- Validazione contrasto WCAG AA: se l'hex selezionato ha contrast ratio insufficiente sul background base (sia light che dark), il picker mostra un warning e propone una versione corretta in luminanza
- Libreria: `colord` (3 KB, modulare, supporto HSL/LCH per i calcoli ruota e contrasto)

Default per nuove categorie: rotazione su una palette tasteful. Il colore viene usato come accento sul bordo dell'`<ArticleCard>` e come pallino accanto al nome categoria nella sidebar.

### `<SourceWizard>`
Wizard 3-step:
1. **URL input** + bottone "Cerca feed". In alternativa, link "Sfoglia fonti suggerite" che apre `<FeaturedSourcesGallery>` (vedi sotto)
2. **Discovery preview** (chiama `POST /yf_sources/discover`): mostra fonti rilevate (RSS o WP API) con anteprima ultimi 3 articoli **+ Open Graph card del sito** (logo, titolo, descrizione, immagine sociale) per dare un'idea visiva immediata; utente sceglie quale aggiungere e in quale categoria
3. **Conferma** + creazione

### `<FeaturedSourcesGallery>`
Lista delle fonti più popolari italiane pre-curate (vedi `featured_sources` in [DATABASE.md](DATABASE.md)). Filtri per categoria suggerita (Cronaca, Sport, Tech, Economia, ...). Ogni fonte ha card con logo + nome + descrizione + bottone "Aggiungi al mio feed". Il backend riusa la `source_id` esistente — non duplica record `sources`.

### `<TimelineFeed>`
Infinite scroll con cursor pagination. Loading skeleton mentre carica. Header con filtri categoria/topic. Pull-to-refresh su mobile.

### `<TopicChip>`
Tag cliccabile che porta a `/me/timeline/topic/:slug` o (su pagine pubbliche di altri utenti) a `/{username}/topic/:slug`.

### `<RssExportButton>`
Mostra l'URL `.../rss` con bottone copia + QR code. Spiega cosa è RSS in tooltip.

### `<CookieBanner>`
Da mostrare al primo accesso. 2 bottoni: "Accetta tutto" / "Rifiuta non essenziali". Apre `PrivacySettingsPage` per scelte fini. Salva consenso in cookie `yf_consent` (1 anno).

### `<ThemeToggle>`
Bottone in header (icona sole/luna). 3 stati ciclici: `system` (default, segue `prefers-color-scheme`), `light`, `dark`. Persistito in `localStorage` `yf_theme`. Inline script in `<head>` di `index.html` legge la preferenza e applica `class="dark"` su `<html>` **prima** del mount Vue → niente flash di tema sbagliato.

Per le pagine Jinja pubbliche, lo stesso script inline è incluso nel `base.html` con la stessa logica → tema coerente attraversando il confine SPA/server-rendered.

### `<OnboardingTour>`
Tour guidato al primo login (driver.js). Step:
1. **Benvenuto** + spiegazione del prodotto
2. **Categorie suggerite a scopo introduttivo**: viene mostrata una rosa di ~10 categorie tematiche (Politica, Cronaca, Sport, Tecnologia, Economia, Cultura, Spettacolo, Esteri, Salute, Motori). L'utente seleziona quelle che gli interessano (anche zero) — diventano categorie effettive nel suo albero. Nessuna è creata di default: l'idea è dare un punto di partenza, non imporre uno schema.
3. **Fonti suggerite**: highlight del link "Sfoglia fonti suggerite" → apre `<FeaturedSourcesGallery>`. L'utente aggiunge una o più fonti popolari nelle categorie scelte (o ne crea di nuove).
4. **Highlight del color picker** sulle categorie create
5. **Highlight del toggle privacy/cookie** con spiegazione FingerprintJS
6. **Highlight del link al feed pubblico** (`/{username}`) — "Questo è il tuo feed visibile a tutti"
7. **"Pronto"** → marca `users.onboarding_completed_at = now()` via `PATCH /yf_me`

Skippabile in qualsiasi momento (anche skip marca `onboarding_completed_at`).

---

## FingerprintJS e privacy

FingerprintJS classifica come tracking sotto GDPR. Quindi:

1. **Default**: NON caricato. Login/register inviano fingerprint placeholder `"none"` finché non c'è consenso
2. **Dopo consenso "Accetta tutto" o "Tracking sì"**: dynamic import del SDK + invio header `X-YF-Fingerprint` su tutte le request
3. **Backend tollerante**: `auth_sessions.fingerprint` può essere `"none"` o un hash. Le funzionalità "device management" e "session theft detection" funzionano solo per sessioni con fingerprint reale
4. **Revoca consenso**: rimuove il fingerprint dalla sessione corrente (UPDATE `auth_sessions.fingerprint = 'none'`)

Cookie banner blocca FingerprintJS, ma NON il cookie session: il cookie session è strettamente necessario al funzionamento e quindi esente dal consenso (cookie tecnici).

---

## Stile e design system

### Tailwind
Configurazione condivisa tra Vue (importata da `src/style.css`) e Jinja (linkata in `<head>`). Stesso `tailwind.config.js` con `content` esteso a `templates/**/*.html` per il purge.

### Tipografia
Font system: **Inter** (per UI) + **Source Serif Pro** (per i titoli articolo nelle pagine pubbliche, look editoriale). Self-hosted con `@font-face` (no Google Fonts CDN per evitare flag GDPR).

### Identità visiva
- **Layout**: box/mosaico tipo Pinterest (masonry con CSS columns) per timeline e topic page. Lista orizzontale solo per search results.
- **Stile**: minimalista, spazi ariosi, font ad alta leggibilità (Inter UI + Source Serif Pro per titoli articolo nelle pagine pubbliche)
- **Identificazione articolo**: ogni card ha bordo sinistro nel colore della categoria di appartenenza (riconoscimento immediato della provenienza nella timeline mista)

### Palette
- **Neutri** Tailwind `slate` come base (light/dark mode)
- **Primario** + **accento**: da definire in fase di design (probabile blu deep + un accento caldo)
- **Semantici**: `success` (verde), `warning` (ambra), `danger` (rosso), `info` (blu)
- **Categorie utente**: 16 preset selezionabili dal color picker + hex custom. La saturazione delle preset è calibrata per avere contrasto sufficiente sia in light che in dark mode (l'utente sceglie una sola tonalità che vale per entrambi i temi).
- **Dark mode in v1.0** ✓ (toggle utente, persistito in localStorage)

### Iconografia
**Heroicons** (24/outline e 24/solid) come default. Componente `<Icon name="..." />` come wrapper.

### Componenti UI primitivi
Da `src/components/ui/`: `Button`, `Input`, `Select`, `Checkbox`, `Switch`, `Modal`, `Drawer`, `Toast`, `Tabs`, `Accordion`, `Tooltip`. Costruiti su Headless UI (a11y) + Tailwind.

---

## Responsive e accessibilità

- **Mobile-first**: layout single-column < 768px, sidebar collassabile via drawer
- **Tablet**: 768-1024px, sidebar permanente compatta
- **Desktop**: > 1024px, sidebar + main + secondary panel (es. dettagli articolo)
- **Target**: WCAG AA. Headless UI ci dà focus management, ARIA roles, keyboard nav
- **Test**: axe-core integrato in Playwright

---

## Performance budget

| Metrica | Target |
|---|---|
| Initial JS bundle (logged) | < 200 KB gzipped |
| Initial CSS bundle | < 30 KB gzipped |
| LCP su 4G | < 2.5s |
| FID | < 100ms |
| CLS | < 0.1 |
| Public page TTFB (Cloudflare hit) | < 100ms |
| Public page TTFB (cache miss, FastAPI render) | < 500ms |

Strumenti: code splitting per route, lazy loading immagini con `loading=lazy`, preloading delle font critiche, `<link rel="preconnect">` verso CDN immagini (se introdurremo proxy).

---

## PWA (v1.0 base, v1.2 push)

- v1.0: `manifest.json` + service worker base (cache statics, offline fallback molto minimale, no functionality offline)
- v1.2: SW gestisce push notifications (web-push API), click su notifica apre l'articolo

---

## Struttura cartelle (Vue SPA)

```
frontend/
  index.html
  package.json
  tailwind.config.js
  vite.config.ts
  tsconfig.json
  public/
    favicon.ico
    manifest.json
    sw.js               (v1.2)
  src/
    main.ts             # bootstrap, Pinia, Router, Tailwind
    App.vue
    router/
      index.ts
      guards.ts
    stores/             # vedi sezione Pinia
    services/           # vedi service-layer
    pages/              # route-level views
      auth/
        LoginPage.vue
        RegisterPage.vue
        VerifyEmailTokenPage.vue
        ...
      me/
        TimelinePage.vue
        SourcesPage.vue
        AddSourcePage.vue
        CategoriesPage.vue
        settings/
          AccountSettingsPage.vue
          PrivacySettingsPage.vue
          DevicesPage.vue              (v1.1)
          NotificationsSettingsPage.vue (v1.2)
        AlertsPage.vue                  (v1.2)
        AlertEditorPage.vue             (v1.2)
        NotificationsPage.vue           (v1.1)
      SearchPage.vue                    (v1.1)
    components/
      ui/               # Button, Input, Modal, ...
      ArticleCard.vue
      ArticleList.vue
      CategoryTree.vue
      SourceWizard.vue
      TopicChip.vue
      TimelineFilter.vue
      RssExportButton.vue
      CookieBanner.vue
    composables/
      useAuth.ts
      useFetch.ts
      useTimeline.ts
      useDebounce.ts
      useTracking.ts
    types/
      api.ts            # Zod schemas + types derivati
      domain.ts
    style.css           # @tailwind base/components/utilities
    assets/
      fonts/
      logos/
  tests/
    unit/
    e2e/
```

---

## Struttura cartelle (Jinja templates)

```
backend/
  app/
    templates/
      base.html
      _meta.html              # macro meta tags + Open Graph + JSON-LD
      _header.html            # logo, nav, login/profile pill
      _footer.html
      _article_card.html      # macro riusabile
      _category_tree.html     # macro
      home_public.html
      about.html
      privacy.html
      terms.html
      user/
        profile.html          # /{username}
        category.html         # /{username}/{cat}/{sub?}
        topic.html            # /{username}/topic/{name}
      rss/
        feed.xml              # macro per tutte le varianti RSS
      errors/
        404.html
        500.html
        403.html
    static/                   # CSS Tailwind buildato + asset condivisi
```

I template Jinja generano markup minimale senza JS framework — solo eventuale piccolo script vanilla che:
- Mostra/nasconde un link "Vai al tuo feed" se cookie session presente (no fetch, solo lettura cookie name)
- Inizializza `<CookieBanner>` se mancante consenso (componente standalone, può essere il **medesimo** caricato dalla SPA, in modalità "auto-mount" senza Pinia)

---

## Per release

### v1.0
Tutte le pagine Jinja pubbliche complete; SPA con auth (register/login/verify), `/me/timeline`, `/me/sources`, `/me/sources/add` (wizard), `/me/categories`, `/me/settings/account` (con GDPR export/delete), `/me/settings/privacy`. Cookie banner. Sitemap dinamica.

### v1.1
SPA: `/me/notifications`, `/search`, `/forgot-password`, `/reset-password`, `/oauth-callback`, `/me/settings/devices`. Possibile dark mode toggle.

### v1.2
SPA: `/me/alerts`, `/me/settings/notifications`. Service worker push completo. Centro notifiche con push.

### v2.0
SPA: dashboard di engagement, topic correlati nelle pagine timeline/topic, eventuali widget di reco. Mobile Android app (Compose) condivide solo i contratti API.

---

## Decisioni fissate (recenti)
- Dark/Light mode con toggle utente, persistito in localStorage ✓
- Layout box/mosaico tipo Pinterest (masonry CSS columns) ✓
- Categorie con colore assegnabile, usato come bordo card per identificazione visiva ✓
- Color picker con ruota colori (complementare/analogo/triadico) + validazione contrasto WCAG AA ✓
- Categorie suggerite a scopo introduttivo (rosa di ~10, l'utente sceglie le sue) ✓
- Fonti suggerite popolari italiane (gallery dedicata in `<FeaturedSourcesGallery>`) ✓
- Tour guidato al primo login con `Driver.js` ✓
- Componente preview Open Graph in `<SourceWizard>` ✓
- Immagini scaricate localmente in due varianti WebP (vedi [INGESTION.md](INGESTION.md) e [DATABASE.md](DATABASE.md)) ✓
- Export GDPR formato ZIP con JSON ✓

## Da definire

- **Palette primario/accento + logo + favicon set** (decisione design vera)
- **Errore "fonte non valida"**: messaggio educativo per discovery che ritorna `kind=invalid` (cosa suggeriamo all'utente?)
- **Numero esatto e nomi finali delle categorie suggerite** (10 è una stima)
