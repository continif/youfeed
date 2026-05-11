<template>
  <div>
    <header class="flex items-center justify-between mb-6 gap-3 flex-wrap">
      <h1 class="text-2xl font-semibold">Le mie fonti</h1>
      <RouterLink
        to="/me/sources/add"
        class="px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium"
        >+ Aggiungi fonte</RouterLink
      >
    </header>

    <div
      v-if="!loading && items.length"
      class="mb-4 flex items-center gap-2 text-sm"
    >
      <label for="category-filter" class="text-slate-500">Filtra:</label>
      <select
        id="category-filter"
        :value="activeCategoryId ?? ''"
        class="px-2 py-1 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
        @change="onFilterChange"
      >
        <option value="">Tutte le categorie</option>
        <option
          v-for="c in flatCategories"
          :key="c.id"
          :value="c.id"
        >
          {{ "— ".repeat(c.depth) }}{{ c.name }}
        </option>
      </select>
      <span v-if="activeCategoryId" class="text-slate-500"
        >· {{ filteredItems.length }} di {{ items.length }}</span
      >
    </div>

    <p v-if="loading" class="text-slate-500">Caricamento…</p>
    <p v-if="error" class="text-red-600 dark:text-red-400">{{ error }}</p>

    <p v-if="!loading && items.length === 0 && !error" class="text-slate-500">
      Nessuna fonte ancora. Comincia con
      <RouterLink to="/me/sources/add" class="text-blue-600 hover:underline"
        >Aggiungi la prima fonte</RouterLink
      >.
    </p>

    <p
      v-if="!loading && items.length > 0 && filteredItems.length === 0"
      class="text-slate-500"
    >
      Nessuna fonte in questa categoria.
      <RouterLink to="/me/sources" class="text-blue-600 hover:underline"
        >Mostra tutte</RouterLink
      >.
    </p>

    <ul
      v-if="filteredItems.length"
      class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
    >
      <li
        v-for="us in filteredItems"
        :key="us.id"
        class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-4 flex flex-col gap-2"
      >
        <div class="flex items-center gap-3">
          <img
            v-if="us.source.favicon_url"
            :src="us.source.favicon_url"
            :alt="us.source.title || ''"
            class="w-6 h-6 rounded"
            loading="lazy"
            @error="onFaviconError($event)"
          />
          <div class="flex-1 min-w-0">
            <h2 class="font-medium truncate">
              {{ us.custom_title || us.source.title || us.source.url_site }}
            </h2>
            <p class="text-xs text-slate-500 truncate">{{ us.source.url_feed || us.source.wp_api_root }}</p>
          </div>
          <span
            class="text-[0.7rem] px-2 py-0.5 rounded-full border"
            :class="kindColor(us.source.kind)"
            >{{ us.source.kind }}</span
          >
        </div>
        <div class="flex items-center justify-between text-xs text-slate-500">
          <span>Categoria: <strong>{{ categoryName(us.category_id) }}</strong></span>
          <button
            type="button"
            class="text-red-600 hover:underline"
            @click="onDelete(us)"
          >
            Rimuovi
          </button>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { listMySources, unlinkSource } from "@/services/sources";
import { fetchCategoryTree, flattenTree } from "@/services/categories";
import { extractError } from "@/services/api";
import { useToastsStore } from "@/stores/toasts";
import type { UserSourceOut, CategoryTreeOut } from "@/types/api";

const toasts = useToastsStore();
const route = useRoute();
const router = useRouter();

const items = ref<UserSourceOut[]>([]);
const tree = ref<CategoryTreeOut | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

const flatCategories = computed(() => {
  if (!tree.value) return [];
  return flattenTree(tree.value);
});

const categoriesById = computed(() => {
  return new Map(flatCategories.value.map((c) => [c.id, c.name]));
});

function categoryName(id: number): string {
  return categoriesById.value.get(id) ?? "—";
}

const activeCategoryId = computed<number | null>(() => {
  const v = route.query.category;
  if (typeof v === "string" && v) {
    const n = parseInt(v, 10);
    return Number.isFinite(n) ? n : null;
  }
  return null;
});

const filteredItems = computed(() => {
  if (activeCategoryId.value === null) return items.value;
  return items.value.filter((u) => u.category_id === activeCategoryId.value);
});

function onFilterChange(e: Event) {
  const value = (e.target as HTMLSelectElement).value;
  router.replace({
    path: "/me/sources",
    query: value ? { category: value } : {},
  });
}

function kindColor(kind: string): string {
  if (kind === "rss")
    return "border-orange-200 dark:border-orange-900 text-orange-700 dark:text-orange-300 bg-orange-50 dark:bg-orange-900/20";
  if (kind === "wordpress_api")
    return "border-blue-200 dark:border-blue-900 text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/20";
  return "border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 bg-slate-50";
}

function onFaviconError(e: Event) {
  (e.target as HTMLImageElement).style.display = "none";
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const [list, t] = await Promise.all([listMySources(), fetchCategoryTree()]);
    items.value = list.items;
    tree.value = t;
  } catch (err) {
    const apiErr = await extractError(err);
    error.value = apiErr?.message ?? "Errore nel caricamento.";
  } finally {
    loading.value = false;
  }
}

async function onDelete(us: UserSourceOut) {
  if (!confirm(`Rimuovere "${us.source.title || us.source.url_site}"?`)) return;
  try {
    await unlinkSource(us.id);
    items.value = items.value.filter((x) => x.id !== us.id);
    toasts.success("Fonte rimossa.");
  } catch (err) {
    const apiErr = await extractError(err);
    toasts.error(apiErr?.message ?? "Errore nella rimozione.");
  }
}

onMounted(load);
</script>
