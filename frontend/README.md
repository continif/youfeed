# YOUFEED — Frontend SPA

Vue 3 + Vite + TypeScript + Pinia + Tailwind. Vedi [`../.claude/FRONTEND.md`](../.claude/FRONTEND.md) per il design completo.

## Quickstart

```bash
# Node 20+
npm install
npm run dev      # dev server su http://localhost:5173 (proxy /yf_ → backend:8000)
```

## Comandi

```bash
npm run dev          # dev server con HMR
npm run build        # build di produzione → dist/
npm run preview      # serve la build per smoke test
npm run lint         # eslint
npm run format       # prettier
npm run type-check   # vue-tsc
npm run test:unit    # vitest
npm run test:e2e     # playwright
```

## Struttura

```
src/
  main.ts              # bootstrap (Pinia, Router, App)
  App.vue              # shell layout
  router/              # Vue Router + guards
  stores/              # Pinia stores per dominio
  services/            # API client + service-layer
  pages/               # route-level components
    auth/              # /login, /register, /verify-email, ...
    me/                # /me/* (timeline, sources, categories, settings)
  components/
    ui/                # primitivi (Button, Input, Modal, ...)
    ArticleCard.vue
    CategoryTree.vue
    SourceWizard.vue
    ...
  composables/         # logica riusabile (useAuth, useFetch, useTimeline, ...)
  types/               # tipi condivisi + schemi Zod
  assets/              # font + logo
  style.css            # @tailwind base/components/utilities
```

## Design system

- **Tailwind CSS** con `darkMode: 'class'`. Il toggle utente (`<ThemeToggle>`) scrive su `localStorage[yf_theme]` in `system | light | dark`. Lo script inline in `index.html` applica la classe prima del mount per evitare FOIT.
- **Headless UI** + componenti custom in `src/components/ui/`.
- **Heroicons** via `@heroicons/vue`.
- **Layout masonry** per timeline/topic via CSS columns native (no libreria).

## Routing

Tutto sotto `/me/*` è autenticato (guard `requireAuth`). `/login`, `/register` redirigono a `/me/timeline` se già loggati. Le pagine pubbliche `/{username}/...` sono renderizzate dal backend FastAPI con Jinja2 — la SPA non le gestisce.
