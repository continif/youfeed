// Dati statici per l'onboarding tour: 10 categorie suggerite + step del tour.
// Le categorie qui sono speculari a `infra/seed/categories_suggested.yaml`.

export interface SuggestedCategory {
  slug: string;
  name: string;
  description: string;
  defaultColor: string;
}

export const SUGGESTED_CATEGORIES: SuggestedCategory[] = [
  {
    slug: "politica",
    name: "Politica",
    description: "Notizie politiche italiane e internazionali",
    defaultColor: "#dc2626",
  },
  {
    slug: "cronaca",
    name: "Cronaca",
    description: "Cronaca nazionale e locale",
    defaultColor: "#0ea5e9",
  },
  {
    slug: "sport",
    name: "Sport",
    description: "Calcio, motori, tennis, basket, eventi sportivi",
    defaultColor: "#16a34a",
  },
  {
    slug: "tecnologia",
    name: "Tecnologia",
    description: "Tech, startup, AI, gadget",
    defaultColor: "#7c3aed",
  },
  {
    slug: "economia",
    name: "Economia",
    description: "Mercati, finanza, lavoro, imprese",
    defaultColor: "#ca8a04",
  },
  {
    slug: "cultura",
    name: "Cultura",
    description: "Libri, mostre, eventi culturali",
    defaultColor: "#9333ea",
  },
  {
    slug: "spettacolo",
    name: "Spettacolo",
    description: "Cinema, TV, musica, gossip",
    defaultColor: "#ec4899",
  },
  {
    slug: "esteri",
    name: "Esteri",
    description: "Politica internazionale, geopolitica, conflitti",
    defaultColor: "#0891b2",
  },
  {
    slug: "salute",
    name: "Salute",
    description: "Medicina, benessere, alimentazione",
    defaultColor: "#10b981",
  },
  {
    slug: "motori",
    name: "Motori",
    description: "Auto, moto, F1, MotoGP",
    defaultColor: "#475569",
  },
];

export type OnboardingStepKey =
  | "welcome"
  | "categories"
  | "sources"
  | "color-picker"
  | "privacy"
  | "public-feed"
  | "done";

export interface OnboardingStep {
  key: OnboardingStepKey;
  title: string;
  body: string;
  /** Quando il pulsante "avanti" deve apparire come primario azione (es. "Crea categorie"). */
  primaryActionLabel?: string;
}

export const ONBOARDING_STEPS: OnboardingStep[] = [
  {
    key: "welcome",
    title: "Benvenuto su YouFeed!",
    body: "Ti guidiamo in 6 passi per metterti subito al lavoro: scegli le tue categorie, aggiungi fonti, organizza il tuo feed.",
  },
  {
    key: "categories",
    title: "Scegli le tue categorie",
    body: "Selezione multipla. Le categorie scelte diventeranno l'alberatura iniziale del tuo feed — potrai modificarle in qualsiasi momento.",
    primaryActionLabel: "Crea queste categorie",
  },
  {
    key: "sources",
    title: "Aggiungi qualche fonte",
    body: "Le fonti popolari italiane sono pre-curate e ordinate per categoria. Aggiungile direttamente o salta — puoi tornarci sempre.",
  },
  {
    key: "color-picker",
    title: "Personalizza il colore",
    body: "Ogni categoria può avere un colore: in masonry vedrai una bordatura colorata sui tuoi articoli per riconoscere subito le sezioni.",
  },
  {
    key: "privacy",
    title: "Privacy",
    body: "Accetta o rifiuta il tracciamento. Se rifiuti, non raccogliamo statistiche di lettura e non viene generato nessun fingerprint del tuo browser.",
  },
  {
    key: "public-feed",
    title: "Il tuo feed pubblico",
    body: "Le categorie marcate 'pubbliche' sono visibili sul tuo profilo all'URL youfeed.it/{username} con export RSS automatico.",
  },
  {
    key: "done",
    title: "Tutto pronto!",
    body: "Ora puoi esplorare il tuo feed. Puoi rifare questo tour da Impostazioni → Privacy in qualsiasi momento.",
    primaryActionLabel: "Inizia",
  },
];
