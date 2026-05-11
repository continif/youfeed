<template>
  <section>
    <header class="flex flex-wrap items-center justify-between gap-3 mb-4">
      <h2 class="text-lg font-semibold">Fonti popolari</h2>
      <select
        v-model="selectedCategory"
        class="rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 py-1 text-sm"
      >
        <option value="">Tutte le categorie</option>
        <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
      </select>
    </header>

    <p v-if="loading" class="text-slate-500 text-sm">Caricamento…</p>
    <p v-if="error" class="text-red-600 dark:text-red-400 text-sm">{{ error }}</p>

    <ul
      v-if="visibleItems.length"
      class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
    >
      <li
        v-for="f in visibleItems"
        :key="f.source_id"
        class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-3 flex flex-col gap-2"
      >
        <div class="flex items-center gap-2">
          <img
            v-if="f.source.favicon_url"
            :src="f.source.favicon_url"
            :alt="f.display_name || ''"
            class="w-5 h-5 rounded"
            loading="lazy"
            @error="hideImg"
          />
          <h3 class="font-medium truncate flex-1">{{ f.display_name || f.source.title }}</h3>
        </div>
        <p
          v-if="f.description"
          class="text-xs text-slate-500 line-clamp-2"
        >
          {{ f.description }}
        </p>
        <button
          type="button"
          class="self-start mt-1 text-xs px-2 py-1 rounded-md border border-blue-300 dark:border-blue-800 text-blue-700 dark:text-blue-300 hover:bg-blue-50 dark:hover:bg-blue-900/30"
          :disabled="addingId === f.source_id"
          @click="$emit('select', f)"
        >
          {{ addingId === f.source_id ? "..." : "Aggiungi" }}
        </button>
      </li>
    </ul>

    <p v-if="!loading && visibleItems.length === 0 && !error" class="text-slate-500 text-sm">
      Nessuna fonte in questa categoria.
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { fetchFeatured } from "@/services/sources";
import { extractError } from "@/services/api";
import type { FeaturedSourceItem } from "@/types/api";

defineProps<{ addingId?: number | null }>();
defineEmits<{ (e: "select", item: FeaturedSourceItem): void }>();

const data = ref<Record<string, FeaturedSourceItem[]>>({});
const loading = ref(false);
const error = ref<string | null>(null);
const selectedCategory = ref("");

const categories = computed(() => Object.keys(data.value).sort());

const visibleItems = computed<FeaturedSourceItem[]>(() => {
  if (selectedCategory.value) {
    return data.value[selectedCategory.value] ?? [];
  }
  return Object.values(data.value).flat();
});

function hideImg(e: Event) {
  (e.target as HTMLImageElement).style.display = "none";
}

onMounted(async () => {
  loading.value = true;
  try {
    const res = await fetchFeatured();
    data.value = res.by_category;
  } catch (err) {
    const apiErr = await extractError(err);
    error.value = apiErr?.message ?? "Errore nel caricamento delle fonti popolari.";
  } finally {
    loading.value = false;
  }
});
</script>
