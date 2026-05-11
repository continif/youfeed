<template>
  <div class="max-w-5xl mx-auto p-4">
    <h1 class="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-3">Ricerca</h1>

    <form @submit.prevent="onSubmit" class="flex gap-2 mb-6">
      <input
        v-model="queryDraft"
        type="search"
        placeholder="Cerca articoli, brand, persone…"
        class="flex-1 px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
        autofocus
      />
      <button
        type="submit"
        class="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium transition-colors"
      >
        Cerca
      </button>
    </form>

    <div v-if="loading" class="text-slate-500 dark:text-slate-400 py-8 text-center">
      Cerco…
    </div>

    <div v-else-if="error" class="text-red-600 dark:text-red-400 py-8 text-center">
      Errore nella ricerca: {{ error }}
    </div>

    <div v-else-if="results && results.query && results.total === 0"
         class="text-slate-500 dark:text-slate-400 py-8 text-center">
      Nessun risultato per <strong>“{{ results.query }}”</strong>.
    </div>

    <div v-else-if="results && results.items.length > 0">
      <p class="text-sm text-slate-600 dark:text-slate-400 mb-4">
        <strong>{{ results.total }}</strong> risultati per
        <span class="font-medium text-slate-900 dark:text-slate-100">“{{ results.query }}”</span>
      </p>

      <ul class="space-y-3">
        <li
          v-for="item in results.items"
          :key="item.id"
          class="p-4 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800/50 hover:border-blue-400 dark:hover:border-blue-500 transition-colors"
        >
          <div class="flex gap-3 items-start">
            <img
              v-if="item.image_local_url || item.image_url"
              :src="(item.image_local_url || item.image_url) ?? undefined"
              :alt="item.title"
              class="w-24 h-24 object-cover rounded flex-shrink-0"
              loading="lazy"
            />
            <div class="flex-1 min-w-0">
              <RouterLink
                :to="`/me/article/${item.id}`"
                class="block font-semibold text-slate-900 dark:text-slate-100 hover:text-blue-600 dark:hover:text-blue-400 mb-1"
              >
                <span v-html="highlightSafe(item.highlights.title) || item.title" />
              </RouterLink>
              <p class="text-xs text-slate-500 dark:text-slate-400 mb-2">
                {{ item.source.title }} ·
                <time :datetime="item.published_at">{{ relTime(item.published_at) }}</time>
              </p>
              <p
                v-if="item.highlights.description || item.highlights.content_text || item.description"
                class="text-sm text-slate-700 dark:text-slate-300 line-clamp-3"
                v-html="highlightSafe(item.highlights.description || item.highlights.content_text) || stripHtml(item.description || '').slice(0, 240)"
              />
              <ul v-if="item.topics.length" class="flex flex-wrap gap-1 mt-2">
                <li
                  v-for="t in item.topics.slice(0, 8)"
                  :key="t.id"
                  :class="['text-[0.7rem] px-2 py-0.5 rounded-full border', topicColor(t.type)]"
                >
                  {{ t.display_name }}
                </li>
              </ul>
            </div>
          </div>
        </li>
      </ul>

      <div class="flex items-center justify-between mt-6">
        <button
          v-if="offset > 0"
          @click="goPage(offset - limit)"
          class="px-3 py-1.5 rounded border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700"
        >
          ← Indietro
        </button>
        <span class="text-sm text-slate-500 dark:text-slate-400">
          {{ offset + 1 }}-{{ Math.min(offset + limit, results.total) }} di {{ results.total }}
        </span>
        <button
          v-if="offset + limit < results.total"
          @click="goPage(offset + limit)"
          class="px-3 py-1.5 rounded border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700"
        >
          Avanti →
        </button>
      </div>
    </div>

    <div v-else class="text-slate-500 dark:text-slate-400 py-8 text-center">
      Inserisci una query per iniziare.
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { formatDistanceToNow, parseISO } from "date-fns";
import { it } from "date-fns/locale";
import { search as searchApi } from "@/services/search";
import type { SearchOut } from "@/types/api";

const route = useRoute();
const router = useRouter();

const queryDraft = ref<string>(String(route.query.q ?? ""));
const limit = 20;
const offset = ref<number>(Number(route.query.offset ?? 0));

const results = ref<SearchOut | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

async function runSearch(q: string, off: number) {
  if (!q.trim()) {
    results.value = null;
    return;
  }
  loading.value = true;
  error.value = null;
  try {
    results.value = await searchApi(q, { limit, offset: off });
    document.title = `Ricerca: ${q} · YouFeed`;
  } catch (e) {
    error.value = String((e as Error).message ?? e);
  } finally {
    loading.value = false;
  }
}

function onSubmit() {
  router.push({ name: "search", query: { q: queryDraft.value.trim(), offset: 0 } });
}

function goPage(newOffset: number) {
  router.push({ name: "search", query: { q: queryDraft.value.trim(), offset: newOffset } });
}

watch(
  () => [route.query.q, route.query.offset],
  ([q, off]) => {
    const queryStr = String(q ?? "");
    const offsetNum = Number(off ?? 0);
    queryDraft.value = queryStr;
    offset.value = offsetNum;
    runSearch(queryStr, offsetNum);
  },
  { immediate: true },
);

function highlightSafe(html: string | undefined): string | null {
  if (!html) return null;
  // Manticore restituisce <mark>...</mark> già escapando il resto, ma per
  // sicurezza ripuliamo a un set di tag minimal.
  return html.replace(/<(?!\/?mark\b)[^>]+>/g, "");
}

function stripHtml(s: string): string {
  return s.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
}

function relTime(iso: string): string {
  try {
    return formatDistanceToNow(parseISO(iso), { addSuffix: true, locale: it });
  } catch {
    return "";
  }
}

function topicColor(type: string): string {
  if (type === "brand")
    return "border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/20";
  if (type === "person")
    return "border-blue-200 dark:border-blue-900 text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/20";
  if (type === "subject")
    return "border-emerald-200 dark:border-emerald-900 text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-900/20";
  return "border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-700/40";
}
</script>

<style scoped>
:deep(mark) {
  background: #fef3c7;
  color: #92400e;
  padding: 0 2px;
  border-radius: 2px;
}
.dark :deep(mark) {
  background: rgba(254, 240, 138, 0.25);
  color: #fde68a;
}
</style>
