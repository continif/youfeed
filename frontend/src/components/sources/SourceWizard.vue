<template>
  <div class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-6">
    <ol class="flex items-center gap-2 text-xs mb-6">
      <li
        v-for="(label, idx) in stepLabels"
        :key="idx"
        :class="[
          'px-3 py-1 rounded-full',
          idx + 1 === step
            ? 'bg-blue-600 text-white'
            : idx + 1 < step
              ? 'bg-emerald-200 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-200'
              : 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-400',
        ]"
      >
        {{ idx + 1 }}. {{ label }}
      </li>
    </ol>

    <!-- Step 1 — URL -->
    <section v-if="step === 1" class="space-y-4">
      <p class="text-sm text-slate-600 dark:text-slate-400">
        Inserisci l'URL del sito o del feed RSS. YouFeed proverà a riconoscere
        automaticamente i feed disponibili o un'API WordPress.
      </p>
      <form @submit.prevent="onDiscover">
        <input
          v-model="url"
          type="url"
          required
          placeholder="https://www.example.com"
          class="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2"
          :disabled="discovering"
        />
        <p v-if="discoverError" class="mt-2 text-sm text-red-600 dark:text-red-400">
          {{ discoverError }}
        </p>
        <button
          type="submit"
          :disabled="discovering || !url"
          class="mt-3 w-full rounded-md bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 disabled:opacity-50"
        >
          {{ discovering ? "Analisi in corso…" : "Analizza" }}
        </button>
      </form>
    </section>

    <!-- Step 2 — preview discovery -->
    <section v-if="step === 2 && discovery" class="space-y-4">
      <div class="flex items-center gap-3">
        <img
          v-if="discovery.og.favicon"
          :src="discovery.og.favicon"
          alt=""
          class="w-8 h-8 rounded"
          loading="lazy"
        />
        <div class="flex-1 min-w-0">
          <h3 class="font-semibold truncate">{{ discovery.og.title || "Sito" }}</h3>
          <p class="text-xs text-slate-500 truncate">{{ discovery.url_site }}</p>
        </div>
        <span
          class="text-xs px-2 py-0.5 rounded-full border"
          :class="kindColor(discovery.kind)"
          >{{ discovery.kind }}</span
        >
      </div>

      <p v-if="discovery.og.description" class="text-sm text-slate-600 dark:text-slate-400">
        {{ discovery.og.description }}
      </p>

      <!-- Multi-feed: lascia scegliere -->
      <div v-if="discovery.candidates.length > 1" class="space-y-2">
        <p class="text-sm font-medium">Feed disponibili:</p>
        <div
          v-for="c in discovery.candidates"
          :key="c.url_feed"
          :class="[
            'rounded-md border p-3 cursor-pointer',
            chosenFeedUrl === c.url_feed
              ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/30'
              : 'border-slate-200 dark:border-slate-700',
          ]"
          @click="chosenFeedUrl = c.url_feed"
        >
          <div class="flex justify-between text-sm">
            <strong>{{ c.title || c.url_feed }}</strong>
            <span class="text-xs text-slate-500">{{ c.sample_articles.length }} articoli</span>
          </div>
          <ul class="mt-1 text-xs text-slate-500 list-disc list-inside">
            <li v-for="(a, i) in c.sample_articles.slice(0, 2)" :key="i" class="truncate">
              {{ a.title }}
            </li>
          </ul>
        </div>
      </div>

      <div class="flex gap-2 pt-2">
        <button
          type="button"
          class="flex-1 rounded-md border border-slate-300 dark:border-slate-700 py-2"
          @click="back()"
        >
          ← Indietro
        </button>
        <button
          type="button"
          class="flex-1 rounded-md bg-blue-600 hover:bg-blue-700 text-white py-2 disabled:opacity-50"
          :disabled="!sourceIdToLink"
          @click="step = 3"
        >
          Continua →
        </button>
      </div>
    </section>

    <!-- Step 3 — categoria -->
    <section v-if="step === 3" class="space-y-4">
      <p class="text-sm text-slate-600 dark:text-slate-400">
        Scegli la categoria a cui aggiungere questa fonte. Puoi anche
        crearne una nuova.
      </p>

      <div v-if="!showNewCat">
        <label class="block text-sm font-medium mb-1">Categoria</label>
        <select
          v-model="categoryId"
          class="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2"
        >
          <option :value="null" disabled>Seleziona…</option>
          <option v-for="c in flatCategories" :key="c.id" :value="c.id">
            {{ "—".repeat(c.depth) }} {{ c.name }}
          </option>
        </select>
        <button
          type="button"
          class="mt-2 text-sm text-blue-600 hover:underline"
          @click="showNewCat = true"
        >
          + Crea nuova categoria
        </button>
      </div>

      <div v-else class="space-y-2">
        <label class="block text-sm font-medium">Nome della nuova categoria</label>
        <input
          v-model="newCatName"
          type="text"
          maxlength="120"
          required
          class="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2"
        />
        <button
          type="button"
          class="text-xs text-slate-500 hover:underline"
          @click="
            () => {
              showNewCat = false;
              newCatName = '';
            }
          "
        >
          Usa categoria esistente
        </button>
      </div>

      <p v-if="linkError" class="text-sm text-red-600 dark:text-red-400">{{ linkError }}</p>

      <div class="flex gap-2 pt-2">
        <button
          type="button"
          class="flex-1 rounded-md border border-slate-300 dark:border-slate-700 py-2"
          :disabled="linking"
          @click="step = 2"
        >
          ← Indietro
        </button>
        <button
          type="button"
          class="flex-1 rounded-md bg-blue-600 hover:bg-blue-700 text-white py-2 disabled:opacity-50"
          :disabled="linking || !canConfirm"
          @click="onConfirm"
        >
          {{ linking ? "Salvataggio…" : "Aggiungi" }}
        </button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { discoverUrl, linkSource } from "@/services/sources";
import { fetchCategoryTree, createCategory, flattenTree } from "@/services/categories";
import { extractError } from "@/services/api";
import type {
  CategoryTreeOut,
  DiscoveryOut,
  FeaturedSourceItem,
} from "@/types/api";

const stepLabels = ["URL", "Anteprima", "Categoria"] as const;
const emit = defineEmits<{ (e: "added", userSourceId: number): void }>();

const step = ref<1 | 2 | 3>(1);
const url = ref("");
const discovery = ref<DiscoveryOut | null>(null);
const chosenFeedUrl = ref<string | null>(null);
const discoverError = ref<string | null>(null);
const discovering = ref(false);

const tree = ref<CategoryTreeOut | null>(null);
const categoryId = ref<number | null>(null);
const showNewCat = ref(false);
const newCatName = ref("");
const linkError = ref<string | null>(null);
const linking = ref(false);

const flatCategories = computed(() => (tree.value ? flattenTree(tree.value) : []));

const sourceIdToLink = computed(() => discovery.value?.source_id ?? null);
const canConfirm = computed(
  () => sourceIdToLink.value !== null && (categoryId.value !== null || newCatName.value.length > 0),
);

onMounted(async () => {
  try {
    tree.value = await fetchCategoryTree();
  } catch {
    /* gestito alla submit */
  }
});

async function onDiscover() {
  discoverError.value = null;
  discovering.value = true;
  try {
    const res = await discoverUrl(url.value);
    discovery.value = res;
    if (res.kind === "invalid") {
      discoverError.value = res.reason ?? "URL non riconosciuta.";
      return;
    }
    if (res.candidates.length > 0) {
      chosenFeedUrl.value = res.candidates[0].url_feed;
    }
    step.value = 2;
  } catch (err) {
    const apiErr = await extractError(err);
    discoverError.value = apiErr?.message ?? "Errore durante l'analisi.";
  } finally {
    discovering.value = false;
  }
}

async function onConfirm() {
  linkError.value = null;
  linking.value = true;
  try {
    let catId = categoryId.value;
    if (showNewCat.value && newCatName.value) {
      const created = await createCategory(newCatName.value);
      catId = created.id;
    }
    if (!catId || !sourceIdToLink.value) {
      linkError.value = "Seleziona una categoria.";
      return;
    }
    const us = await linkSource(sourceIdToLink.value, catId);
    emit("added", us.id);
  } catch (err) {
    const apiErr = await extractError(err);
    linkError.value = apiErr?.message ?? "Errore nel salvataggio.";
  } finally {
    linking.value = false;
  }
}

function back() {
  step.value = 1;
  discovery.value = null;
}

/** Pre-popola con una FeaturedSource (chiamata dall'esterno via ref). */
function presetFromFeatured(item: FeaturedSourceItem) {
  discovery.value = {
    kind: item.source.kind as "rss" | "wordpress_api",
    source_id: item.source_id,
    url_site: item.source.url_site,
    url_feed: item.source.url_feed,
    wp_api_root: item.source.wp_api_root,
    candidates: [],
    og: {
      title: item.display_name ?? item.source.title,
      description: item.description,
      image: null,
      site_name: null,
      favicon: item.source.favicon_url,
    },
    reason: null,
  };
  chosenFeedUrl.value = item.source.url_feed;
  step.value = 3;
}

function kindColor(kind: string): string {
  if (kind === "rss")
    return "border-orange-200 dark:border-orange-900 text-orange-700 dark:text-orange-300 bg-orange-50 dark:bg-orange-900/20";
  if (kind === "wordpress_api")
    return "border-blue-200 dark:border-blue-900 text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/20";
  return "border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/20";
}

defineExpose({ presetFromFeatured });
</script>
