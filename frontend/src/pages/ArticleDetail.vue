<template>
  <div>
    <div class="mb-4">
      <RouterLink to="/me/feed" class="text-sm text-blue-600 hover:underline">
        ← Torna al feed
      </RouterLink>
    </div>

    <div v-if="loading" class="text-slate-500">Caricamento...</div>
    <div v-else-if="error" class="text-red-600">
      Articolo non disponibile: {{ error }}
    </div>

    <div v-else-if="article" class="grid gap-6 md:grid-cols-3">
      <!-- Articolo principale (col 1-2 desktop, full mobile) -->
      <article
        class="md:col-span-2 bg-white dark:bg-slate-800 rounded-lg overflow-hidden shadow-md"
        :class="{ 'border-2': true }"
        :style="
          article.category_color
            ? { borderColor: article.category_color, borderWidth: '3px' }
            : { borderColor: 'rgb(203 213 225 / 1)' }
        "
      >
        <div v-if="hasImage" class="relative">
          <picture>
            <source
              v-if="article.image_local_url"
              media="(max-width: 599px)"
              :srcset="article.image_local_url.replace('_d.webp', '_m.webp')"
            />
            <img
              :src="article.image_local_url || article.image_url || ''"
              :alt="article.title"
              class="w-full h-auto block"
              @error="imageFailed = true"
            />
          </picture>
          <!-- Bookmark toggle: overlay angolo alto-destra, stesso stile della card -->
          <button
            type="button"
            class="absolute right-3 top-3 w-10 h-10 flex items-center justify-center rounded-md text-lg leading-none transition-colors"
            :class="
              isBookmarked
                ? 'bg-blue-600 hover:bg-blue-700 text-white ring-1 ring-white/60'
                : 'bg-black/70 hover:bg-black/85 text-white'
            "
            :title="isBookmarked ? 'Rimuovi dai salvati' : 'Salva articolo'"
            :aria-label="isBookmarked ? 'Rimuovi dai salvati' : 'Salva articolo'"
            :aria-pressed="isBookmarked"
            @click="onToggleBookmark"
          >💾</button>
        </div>

        <div class="p-6">
          <h1 class="text-2xl font-semibold leading-tight mb-2 flex items-start gap-3">
            <span class="flex-1">{{ article.title }}</span>
            <button
              v-if="!hasImage"
              type="button"
              class="w-9 h-9 flex items-center justify-center rounded-md text-base leading-none shrink-0 transition-colors"
              :class="
                isBookmarked
                  ? 'bg-blue-600 hover:bg-blue-700 text-white'
                  : 'bg-black/80 hover:bg-black text-white'
              "
              :title="isBookmarked ? 'Rimuovi dai salvati' : 'Salva articolo'"
              :aria-label="isBookmarked ? 'Rimuovi dai salvati' : 'Salva articolo'"
              :aria-pressed="isBookmarked"
              @click="onToggleBookmark"
            >💾</button>
          </h1>
          <div class="flex items-center justify-between text-sm text-slate-500 mb-4">
            <span class="font-medium">{{
              article.source.title || article.source.url_site
            }}</span>
            <time :datetime="article.published_at">{{ relTime }}</time>
          </div>

          <ul v-if="article.topics.length" class="flex flex-wrap gap-1 mb-4">
            <li
              v-for="t in displayedTopics"
              :key="t.id"
              :class="['text-xs px-2 py-0.5 rounded-full border', topicColor(t.type)]"
            >
              {{ t.display_name }}
            </li>
            <li
              v-if="article.topics.length > MAX_TOPICS"
              class="text-xs px-2 py-0.5 rounded-full border text-slate-500 dark:text-slate-400 border-slate-300 dark:border-slate-600"
              :title="`${article.topics.length - MAX_TOPICS} altri topic`"
            >
              +{{ article.topics.length - MAX_TOPICS }}
            </li>
          </ul>

          <p v-if="article.description" class="text-base text-slate-700 dark:text-slate-300 mb-4">
            {{ cleanDescription }}
          </p>

          <div
            v-if="contentPreview.expanded && article.content_html"
            class="prose prose-slate dark:prose-invert max-w-none"
            v-html="article.content_html"
          />
          <div
            v-else-if="contentPreview.html"
            class="prose prose-slate dark:prose-invert max-w-none"
            v-html="contentPreview.html"
          />

          <button
            v-if="contentPreview.truncated"
            type="button"
            class="mt-3 text-sm text-blue-600 hover:underline"
            @click="contentExpanded = !contentExpanded"
          >
            {{ contentExpanded ? "Riduci" : "Mostra tutto" }}
          </button>

          <a
            :href="article.url_canonical"
            target="_blank"
            rel="noopener"
            class="inline-block mt-6 px-4 py-2 rounded-md bg-blue-600 text-white text-sm hover:bg-blue-700"
          >
            Apri articolo originale ↗
          </a>
        </div>
      </article>

      <!-- Sidebar correlati (col 3 desktop, sotto mobile) -->
      <aside class="md:col-span-1">
        <header class="mb-3 flex items-center justify-between">
          <h2 class="font-semibold text-lg">Notizie correlate</h2>
        </header>

        <!-- Toggle formula (debug A/B test) -->
        <div class="mb-3 flex gap-1 text-xs">
          <button
            v-for="f in formulas"
            :key="f"
            type="button"
            @click="formula = f"
            class="px-2 py-1 rounded border"
            :class="
              formula === f
                ? 'bg-blue-600 text-white border-blue-600'
                : 'border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700'
            "
          >
            {{ f }}
          </button>
        </div>

        <div v-if="relatedLoading" class="text-sm text-slate-500">Cercando...</div>
        <div v-else-if="related && related.items.length === 0" class="text-sm text-slate-500">
          Nessun articolo simile (overlap ≥ {{ Math.round(related.min_overlap * 100) }}%
          nei ±{{ related.days_window }} giorni).
        </div>
        <ul v-else-if="related" class="space-y-2">
          <li v-for="r in related.items" :key="r.id">
            <RouterLink
              :to="`/me/article/${r.id}`"
              class="block p-3 rounded-md border bg-white dark:bg-slate-800 hover:shadow-md dark:hover:shadow-white/10 transition-shadow"
              :style="
                r.category_color
                  ? { borderColor: r.category_color, borderWidth: '2px' }
                  : {}
              "
            >
              <div class="text-xs text-slate-500 mb-1 flex justify-between">
                <span>{{ r.source.title }}</span>
                <span>{{ Math.round(r.overlap * 100) }}%</span>
              </div>
              <h3 class="text-sm font-medium leading-snug">{{ r.title }}</h3>
            </RouterLink>
          </li>
        </ul>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { formatDistanceToNow, parseISO } from "date-fns";
import { it } from "date-fns/locale";
import { fetchArticle, fetchRelatedArticles } from "@/services/articles";
import { useAuthStore } from "@/stores/auth";
import { useBookmarksStore } from "@/stores/bookmarks";
import { useToastsStore } from "@/stores/toasts";
import type {
  ArticleDetailOut,
  RelatedArticlesOut,
  RelatedFormula,
} from "@/types/api";

const route = useRoute();
const auth = useAuthStore();
const bookmarksStore = useBookmarksStore();
const toasts = useToastsStore();

const formulas: RelatedFormula[] = ["coverage", "source", "max", "jaccard"];
const formula = ref<RelatedFormula>("coverage");

const MAX_TOPICS = 12;

const article = ref<ArticleDetailOut | null>(null);
const related = ref<RelatedArticlesOut | null>(null);
const loading = ref(true);
const relatedLoading = ref(false);
const error = ref<string | null>(null);
const imageFailed = ref(false);
const contentExpanded = ref(false);

const CONTENT_PREVIEW_LIMIT = 1000;

const isBookmarked = computed(() =>
  article.value ? bookmarksStore.isBookmarked(article.value.id) : false,
);

async function onToggleBookmark() {
  if (!article.value) return;
  if (!auth.isAuthenticated) {
    toasts.error("Accedi per salvare gli articoli.");
    return;
  }
  try {
    await bookmarksStore.toggle(article.value.id);
  } catch {
    toasts.error("Impossibile aggiornare il bookmark.");
  }
}

const articleId = computed(() => Number(route.params.id));

const displayedTopics = computed(() =>
  article.value ? article.value.topics.slice(0, MAX_TOPICS) : [],
);

const hasImage = computed(
  () =>
    !imageFailed.value &&
    article.value !== null &&
    !!(article.value.image_local_url || article.value.image_url),
);

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function htmlToText(html: string): string {
  // Mantiene i confini di paragrafo prima di togliere i tag: i </p> </div>
  // </h2…> </li> </br> diventano "\n", così il regex `\.\n` può poi trovare
  // il primo paragrafo che termina in punto + newline.
  const withBreaks = html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|h[1-6]|li|blockquote|tr)>/gi, "\n");
  const tmp = document.createElement("div");
  tmp.innerHTML = withBreaks;
  return (tmp.textContent || "").replace(/\r\n?/g, "\n");
}

const contentPreview = computed<{
  html: string;
  truncated: boolean;
  expanded: boolean;
}>(() => {
  const a = article.value;
  if (!a) return { html: "", truncated: false, expanded: false };
  // content_text può essere null/vuoto: in quel caso derivo dal content_html
  // preservando i salti di paragrafo.
  let text = (a.content_text ?? "").trim();
  if (!text && a.content_html) text = htmlToText(a.content_html).trim();
  if (!text || text.length <= CONTENT_PREVIEW_LIMIT) {
    return { html: a.content_html ?? "", truncated: false, expanded: true };
  }
  // Primo paragrafo = testo fino al primo `.\n` (incluso il punto).
  const firstMatch = text.match(/^([\s\S]*?\.)\s*\n/);
  const first = (firstMatch ? firstMatch[1] : text.split(/\n/)[0]).trim();
  // Ultimo paragrafo = ultima riga non vuota.
  const lines = text.split(/\n+/).map((l: string) => l.trim()).filter(Boolean);
  const last = lines.length ? lines[lines.length - 1] : "";
  if (!first || !last || first === last) {
    return { html: a.content_html ?? "", truncated: false, expanded: true };
  }
  const html =
    `<p>${escapeHtml(first)}</p>` +
    `<p class="text-slate-400 text-center select-none my-3">[…]</p>` +
    `<p>${escapeHtml(last)}</p>`;
  return { html, truncated: true, expanded: contentExpanded.value };
});

const cleanDescription = computed(() => {
  const raw = article.value?.description ?? "";
  if (!raw) return "";
  const tmp = document.createElement("div");
  tmp.innerHTML = raw;
  return (tmp.textContent || "").replace(/\s+/g, " ").trim();
});

const relTime = computed(() => {
  if (!article.value?.published_at) return "";
  try {
    return formatDistanceToNow(parseISO(article.value.published_at), {
      locale: it,
      addSuffix: true,
    });
  } catch {
    return article.value.published_at;
  }
});

function topicColor(type: string): string {
  if (type === "brand")
    return "border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/20";
  if (type === "person")
    return "border-blue-200 dark:border-blue-900 text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/20";
  if (type === "subject")
    return "border-emerald-200 dark:border-emerald-900 text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-900/20";
  return "border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-700/40";
}

async function loadArticle() {
  loading.value = true;
  error.value = null;
  imageFailed.value = false;
  try {
    article.value = await fetchArticle(articleId.value);
    await loadRelated();
  } catch (e) {
    error.value = String((e as Error).message ?? e);
  } finally {
    loading.value = false;
  }
}

async function loadRelated() {
  relatedLoading.value = true;
  try {
    related.value = await fetchRelatedArticles(articleId.value, {
      formula: formula.value,
      days: 15,
      minOverlap: 0.4,
      limit: 20,
    });
  } catch {
    related.value = { items: [], formula: formula.value, min_overlap: 0.4, days_window: 15 };
  } finally {
    relatedLoading.value = false;
  }
}

watch(articleId, loadArticle, { immediate: true });
// Cambio formula → ricarica solo correlati
watch(formula, () => {
  if (article.value) loadRelated();
});

// Imposta il titolo del tab al titolo della notizia, ripristina alla baseline
// quando l'utente lascia la pagina (evita "Sony Xperia 1 VIII… | YouFeed"
// persistente su altre route).
const DEFAULT_TITLE = "YouFeed";
watch(
  () => article.value?.title,
  (t) => {
    document.title = t ? `${t} · YouFeed` : DEFAULT_TITLE;
  },
);
onUnmounted(() => {
  document.title = DEFAULT_TITLE;
});
</script>
