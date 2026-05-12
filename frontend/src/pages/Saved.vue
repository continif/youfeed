<template>
  <div class="max-w-3xl">
    <div class="flex items-center justify-between mb-6 gap-2 flex-wrap">
      <h1 class="text-2xl font-semibold flex items-center gap-2">
        <span aria-hidden="true">💾</span>
        <span>Salvati</span>
      </h1>
      <span v-if="!loading && items.length" class="text-xs text-slate-500 dark:text-slate-400">
        {{ items.length }} articol{{ items.length === 1 ? "o" : "i" }}
      </span>
    </div>

    <p class="text-sm text-slate-600 dark:text-slate-400 mb-6">
      I tuoi articoli salvati. Usa l'icona 💾 sulle card o sul dettaglio per
      aggiungere/rimuovere bookmark.
    </p>

    <div v-if="loading" class="text-sm text-slate-500 dark:text-slate-400 py-6 text-center">
      Carico…
    </div>

    <div v-else-if="error" class="text-sm text-red-600 dark:text-red-400 py-6 text-center">
      {{ error }}
    </div>

    <ul v-else-if="items.length" class="space-y-4">
      <li v-for="b in items" :key="b.article.id">
        <ArticleCard :item="b.article" />
        <p class="text-xs text-slate-400 dark:text-slate-500 mt-1 ml-1">
          Salvato {{ relTime(b.created_at) }}
        </p>
      </li>
    </ul>

    <div v-else class="text-center py-12">
      <p class="text-4xl mb-2" aria-hidden="true">💾</p>
      <p class="text-sm text-slate-500 dark:text-slate-400">
        Nessun articolo salvato. Inizia ad aggiungere bookmark dal feed.
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { formatDistanceToNow, parseISO } from "date-fns";
import { it } from "date-fns/locale";
import ArticleCard from "@/components/articles/ArticleCard.vue";
import { listBookmarks } from "@/services/bookmarks";
import { useBookmarksStore } from "@/stores/bookmarks";
import type { BookmarkOut } from "@/types/api";

const bookmarksStore = useBookmarksStore();

const items = ref<BookmarkOut[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    items.value = await listBookmarks({ limit: 100 });
    // Popola lo store così le icone su altre pagine sono consistenti.
    await bookmarksStore.hydrate(items.value.map((b) => b.article.id));
  } catch (e) {
    error.value = String((e as Error).message ?? e);
  } finally {
    loading.value = false;
  }
}

function relTime(iso: string): string {
  try {
    return formatDistanceToNow(parseISO(iso), { addSuffix: true, locale: it });
  } catch {
    return "";
  }
}

onMounted(load);
</script>
