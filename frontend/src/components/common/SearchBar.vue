<template>
  <div class="relative" v-click-outside="close">
    <form @submit.prevent="onSubmit" class="flex items-center">
      <div class="relative w-full">
        <svg
          class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 dark:text-slate-500 pointer-events-none"
          xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
          aria-hidden="true"
        >
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input
          ref="inputEl"
          v-model="query"
          type="search"
          placeholder="Cerca…"
          class="w-full pl-9 pr-3 py-1.5 text-sm rounded-full border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          @focus="open = true"
          @input="onInput"
          @keydown.escape="close"
        />
      </div>
    </form>

    <div
      v-if="open && suggestions && (suggestions.topics.length || suggestions.sources.length)"
      class="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg z-30 max-h-96 overflow-y-auto"
    >
      <div v-if="suggestions.topics.length" class="py-1">
        <div class="px-3 py-1 text-[0.65rem] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">
          Topics
        </div>
        <button
          v-for="t in suggestions.topics"
          :key="`t-${t.id}`"
          type="button"
          class="w-full text-left px-3 py-1.5 text-sm hover:bg-slate-100 dark:hover:bg-slate-700 flex items-center justify-between"
          @click="selectTopic(t.display_name)"
        >
          <span class="text-slate-900 dark:text-slate-100 truncate">{{ t.display_name }}</span>
          <span :class="['text-[0.65rem] px-1.5 py-0.5 rounded-full border ml-2', topicColor(t.type)]">
            {{ t.type }}
          </span>
        </button>
      </div>
      <div v-if="suggestions.sources.length" class="py-1 border-t border-slate-100 dark:border-slate-700">
        <div class="px-3 py-1 text-[0.65rem] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">
          Fonti
        </div>
        <button
          v-for="s in suggestions.sources"
          :key="`s-${s.id}`"
          type="button"
          class="w-full text-left px-3 py-1.5 text-sm hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-900 dark:text-slate-100 truncate"
          @click="selectSource(s.title || '')"
        >
          {{ s.title || s.url_site }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, type DirectiveBinding } from "vue";
import { useRouter } from "vue-router";
import { suggest as suggestApi } from "@/services/search";
import type { SuggestOut } from "@/types/api";

const router = useRouter();
const inputEl = ref<HTMLInputElement | null>(null);
const query = ref("");
const open = ref(false);
const suggestions = ref<SuggestOut | null>(null);

let debounceTimer: number | null = null;
function onInput() {
  open.value = true;
  if (debounceTimer) window.clearTimeout(debounceTimer);
  debounceTimer = window.setTimeout(loadSuggestions, 250);
}

async function loadSuggestions() {
  const q = query.value.trim();
  if (q.length < 2) {
    suggestions.value = null;
    return;
  }
  try {
    suggestions.value = await suggestApi(q, 8);
  } catch {
    suggestions.value = null;
  }
}

function onSubmit() {
  const q = query.value.trim();
  if (!q) return;
  open.value = false;
  router.push({ name: "search", query: { q } });
}

function selectTopic(name: string) {
  query.value = name;
  open.value = false;
  router.push({ name: "search", query: { q: name } });
}
function selectSource(name: string) {
  query.value = name;
  open.value = false;
  router.push({ name: "search", query: { q: name } });
}

function close() {
  open.value = false;
}

// Reset al cambio rotta verso una NON-search page
watch(
  () => router.currentRoute.value.name,
  (name) => {
    if (name !== "search") {
      query.value = "";
      open.value = false;
    }
  },
);

// Direttiva click-outside locale (no plugin)
const vClickOutside = {
  mounted(el: HTMLElement, binding: DirectiveBinding<() => void>) {
    const handler = (e: MouseEvent) => {
      if (!el.contains(e.target as Node)) binding.value();
    };
    (el as HTMLElement & { _coClick?: (e: MouseEvent) => void })._coClick = handler;
    document.addEventListener("click", handler);
  },
  beforeUnmount(el: HTMLElement) {
    const ref_ = (el as HTMLElement & { _coClick?: (e: MouseEvent) => void })._coClick;
    if (ref_) document.removeEventListener("click", ref_);
  },
};

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
