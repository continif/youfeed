<template>
  <div>
    <p v-if="loading && items.length === 0" class="text-slate-500">Caricamento…</p>
    <p v-if="errorMessage" class="text-red-600 dark:text-red-400">{{ errorMessage }}</p>

    <div
      v-if="items.length"
      class="columns-1 sm:columns-2 lg:columns-3 xl:columns-4 gap-4"
    >
      <ArticleCard v-for="item in items" :key="item.id" :item="item" />
    </div>

    <p v-if="items.length === 0 && !loading && !errorMessage" class="text-slate-500">
      <slot name="empty">
        Nessun articolo. Aggiungi delle fonti per popolare il feed.
      </slot>
    </p>

    <p v-if="nextCursor" class="text-center mt-6">
      <button
        type="button"
        :disabled="loading"
        class="px-4 py-2 rounded-md border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50"
        @click="loadMore"
      >
        {{ loading ? "Caricamento…" : "Carica altri" }}
      </button>
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { extractError } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import { useBookmarksStore } from "@/stores/bookmarks";
import type { ArticleListItem, ArticleListOut } from "@/types/api";
import ArticleCard from "@/components/articles/ArticleCard.vue";

const auth = useAuthStore();
const bookmarksStore = useBookmarksStore();

/**
 * `fetcher` riceve un cursor opzionale e ritorna la pagina articoli.
 * Permette di riusare TimelineFeed sia per il feed personale che per il
 * feed pubblico di un username (e in futuro per filtri categoria/topic).
 */
const props = defineProps<{
  fetcher: (cursor?: string) => Promise<ArticleListOut>;
  pageSize?: number;
}>();

const items = ref<ArticleListItem[]>([]);
const nextCursor = ref<string | null>(null);
const loading = ref(false);
const errorMessage = ref<string | null>(null);

async function load(cursor?: string) {
  loading.value = true;
  errorMessage.value = null;
  try {
    const res = await props.fetcher(cursor);
    items.value = cursor ? [...items.value, ...res.items] : res.items;
    nextCursor.value = res.next_cursor;
    if (auth.isAuthenticated && res.items.length) {
      bookmarksStore.hydrate(res.items.map((a: ArticleListItem) => a.id));
    }
  } catch (err) {
    const apiErr = await extractError(err);
    errorMessage.value = apiErr?.message ?? "Errore nel caricamento del feed.";
  } finally {
    loading.value = false;
  }
}

function loadMore() {
  if (nextCursor.value) load(nextCursor.value);
}

defineExpose({ reload: () => load(undefined) });

onMounted(() => load());
</script>
