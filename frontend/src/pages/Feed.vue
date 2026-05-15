<template>
  <div>
    <header class="mb-6">
      <h1 class="text-2xl font-semibold flex items-center flex-wrap gap-x-2 gap-y-1">
        <template v-if="activeCategoryName">
          <RouterLink
            :to="removeCategoryTo"
            class="inline-flex items-center justify-center w-8 h-8 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 hover:bg-red-500 hover:text-white dark:hover:bg-red-500 transition-colors text-base leading-none shadow-sm"
            aria-label="Rimuovi filtro categoria"
            title="Rimuovi categoria"
            >✕</RouterLink
          >
          <span>{{ activeCategoryName }}</span>
        </template>
        <span
          v-if="activeCategoryName && activeTopicId"
          class="text-slate-400 dark:text-slate-500 font-normal"
          >—</span
        >
        <template v-if="activeTopicId">
          <RouterLink
            :to="removeTopicTo"
            class="inline-flex items-center justify-center w-8 h-8 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 hover:bg-red-500 hover:text-white dark:hover:bg-red-500 transition-colors text-base leading-none shadow-sm"
            aria-label="Rimuovi filtro topic"
            title="Rimuovi topic"
            >✕</RouterLink
          >
          <span class="text-blue-600">
            #{{ activeTopicLabel || `topic ${activeTopicId}` }}
          </span>
        </template>
        <span v-if="!activeCategoryName && !activeTopicId">Il mio feed</span>
      </h1>

      <!-- Box info topic — si materializza se il topic ha enrichment Wikidata -->
      <aside
        v-if="hasTopicInfo"
        class="mt-4 p-4 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60"
      >
        <p
          v-if="topicDetail?.description"
          class="text-sm text-slate-700 dark:text-slate-300 leading-snug"
        >
          {{ topicDetail.description }}
        </p>

        <!-- Metadata Wikidata (instance_of, country, owned_by) -->
        <dl
          v-if="hasTopicMeta"
          class="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs"
        >
          <template v-if="topicDetail?.instance_of?.length">
            <dt class="text-slate-500 dark:text-slate-400">È un</dt>
            <dd class="text-slate-700 dark:text-slate-300">
              {{ topicDetail.instance_of.map(qidLabel).join(", ") }}
            </dd>
          </template>
          <template v-if="topicDetail?.country?.length">
            <dt class="text-slate-500 dark:text-slate-400">Paese</dt>
            <dd class="text-slate-700 dark:text-slate-300">
              {{ topicDetail.country.map(qidLabel).join(", ") }}
            </dd>
          </template>
          <template v-if="topicDetail?.owned_by?.length">
            <dt class="text-slate-500 dark:text-slate-400">Posseduta da</dt>
            <dd class="text-slate-700 dark:text-slate-300">
              {{ topicDetail.owned_by.map(qidLabel).join(", ") }}
            </dd>
          </template>
        </dl>

        <div class="mt-3 flex flex-wrap gap-3 text-sm">
          <a
            v-if="topicDetail?.wikipedia_url"
            :href="topicDetail.wikipedia_url"
            target="_blank"
            rel="noopener"
            class="text-blue-600 hover:underline"
          >
            Wikipedia ↗
          </a>
          <a
            v-if="topicDetail?.official_url"
            :href="topicDetail.official_url"
            target="_blank"
            rel="noopener"
            class="text-blue-600 hover:underline"
          >
            Sito ufficiale ↗
          </a>
        </div>
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
import { fetchTopic, type QidRef, type TopicDetailOut } from "@/services/topics";
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

// Dettaglio topic (description + metadata Wikidata) caricato quando attivo
const topicDetail = ref<TopicDetailOut | null>(null);

const hasTopicMeta = computed<boolean>(() => {
  const t = topicDetail.value;
  return !!(
    t &&
    (t.instance_of.length || t.country.length || t.owned_by.length)
  );
});

const hasTopicInfo = computed<boolean>(() => {
  const t = topicDetail.value;
  if (!t) return false;
  return !!(
    t.description ||
    t.wikipedia_url ||
    t.official_url ||
    hasTopicMeta.value
  );
});

function qidLabel(x: QidRef): string {
  return x.label || x.qid;
}

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

// Link per rimuovere SOLO il filtro categoria, preservando il topic attivo
const removeCategoryTo = computed(() => {
  return activeTopicId.value
    ? { path: "/me/feed", query: { topic: String(activeTopicId.value) } }
    : { path: "/me/feed" };
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
