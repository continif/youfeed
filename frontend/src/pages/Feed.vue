<template>
  <div>
    <header class="mb-6">
      <div class="flex items-baseline justify-between gap-3 flex-wrap">
        <h1 class="text-2xl font-semibold">
          <span v-if="activeCategoryName">{{ activeCategoryName }}</span>
          <span v-else-if="activeTopicId" class="text-blue-600">
            #{{ activeTopicLabel || `topic ${activeTopicId}` }}
          </span>
          <span v-else>Il mio feed</span>
        </h1>
        <RouterLink
          v-if="activeCategoryId && !activeTopicId"
          to="/me/feed"
          class="text-sm text-blue-600 hover:underline"
          >× Rimuovi filtro</RouterLink
        >
      </div>
      <div
        v-if="activeTopicId"
        class="mt-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 text-sm text-blue-700 dark:text-blue-300"
      >
        <span>#{{ activeTopicLabel || `topic ${activeTopicId}` }}</span>
        <RouterLink
          :to="removeTopicTo"
          class="ml-1 hover:opacity-75"
          aria-label="Rimuovi filtro topic"
          >×</RouterLink
        >
      </div>

      <!-- Wikipedia box: si materializza se il topic ha description Wikidata -->
      <aside
        v-if="topicDetail && (topicDetail.description || topicDetail.wikipedia_url)"
        class="mt-4 p-4 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60"
      >
        <p
          v-if="topicDetail.description"
          class="text-sm text-slate-700 dark:text-slate-300 leading-snug"
        >
          {{ topicDetail.description }}
        </p>
        <a
          v-if="topicDetail.wikipedia_url"
          :href="topicDetail.wikipedia_url"
          target="_blank"
          rel="noopener"
          class="mt-2 inline-flex items-center gap-1 text-sm text-blue-600 hover:underline"
        >
          Leggi su Wikipedia ↗
        </a>
      </aside>
    </header>

    <TimelineFeed ref="timelineRef" :fetcher="fetcher">
      <template #empty>
        <span v-if="activeCategoryId || activeTopicId">
          Nessun articolo per questo filtro.
          <RouterLink to="/me/feed" class="text-blue-600 hover:underline"
            >Mostra tutto</RouterLink
          >.
        </span>
        <span v-else>
          Nessun articolo.
          <RouterLink to="/me/sources" class="text-blue-600 hover:underline"
            >Aggiungi delle fonti</RouterLink
          >
          per popolare il feed.
        </span>
      </template>
    </TimelineFeed>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import TimelineFeed from "@/components/articles/TimelineFeed.vue";
import { fetchFeed } from "@/services/articles";
import { fetchCategoryTree, flattenTree } from "@/services/categories";
import { fetchTopic, type TopicDetailOut } from "@/services/topics";
import type { CategoryNode } from "@/types/api";

const route = useRoute();

const timelineRef = ref<InstanceType<typeof TimelineFeed> | null>(null);
const categoryTree = ref<CategoryNode[]>([]);

// Path-based: /me/feed/:categoryId. Vuoto su /me/feed (nessun filtro).
const activeCategoryId = computed<number | null>(() => {
  const v = route.params.categoryId;
  if (typeof v === "string" && v) {
    const n = parseInt(v, 10);
    return Number.isFinite(n) ? n : null;
  }
  return null;
});

const activeTopicId = computed<number | null>(() => {
  const v = route.query.topic;
  if (typeof v === "string" && v) {
    const n = parseInt(v, 10);
    return Number.isFinite(n) ? n : null;
  }
  return null;
});

// Label del topic attivo: derivata dal primo articolo del feed che lo include.
// È euristica ma sufficiente per la header (no fetch dedicato).
const activeTopicLabel = ref<string | null>(null);

// Dettaglio topic (description + wikipedia_url) caricato quando attivo
const topicDetail = ref<TopicDetailOut | null>(null);

async function loadTopicDetail(id: number | null) {
  if (!id) {
    topicDetail.value = null;
    return;
  }
  try {
    topicDetail.value = await fetchTopic(id);
  } catch {
    topicDetail.value = null;
  }
}

const activeCategoryName = computed<string | null>(() => {
  if (!activeCategoryId.value) return null;
  const flat = flattenTree({ tree: categoryTree.value });
  const found = flat.find((c) => c.id === activeCategoryId.value);
  return found?.name ?? null;
});

// Link per rimuovere SOLO il filtro topic, preservando la categoria attiva
const removeTopicTo = computed(() => {
  return activeCategoryId.value
    ? `/me/feed/${activeCategoryId.value}`
    : "/me/feed";
});

// Carica l'albero categorie una volta (per visualizzare il nome del filtro)
async function loadTree() {
  try {
    const res = await fetchCategoryTree();
    categoryTree.value = res.tree;
  } catch {
    // silente: il filtro funziona anche senza nome
  }
}
loadTree();

async function fetcher(cursor?: string) {
  const res = await fetchFeed({
    cursor,
    limit: 24,
    category: activeCategoryId.value ?? undefined,
    topic: activeTopicId.value ?? undefined,
  });
  // Deriva la label del topic attivo dal primo articolo che lo contiene
  if (activeTopicId.value && !cursor) {
    activeTopicLabel.value = null;
    for (const item of res.items) {
      const t = item.topics.find((x) => x.id === activeTopicId.value);
      if (t) {
        activeTopicLabel.value = t.display_name;
        break;
      }
    }
  }
  return res;
}

// Reload quando cambia uno dei filtri
watch([activeCategoryId, activeTopicId], () => {
  activeTopicLabel.value = null;
  loadTopicDetail(activeTopicId.value);
  timelineRef.value?.reload();
});

// Carica il dettaglio topic al primo render (se già attivo via deep-link)
loadTopicDetail(activeTopicId.value);
</script>
