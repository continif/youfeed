<template>
  <div class="max-w-2xl">
    <h1 class="text-2xl font-semibold mb-2">Alert</h1>
    <p class="text-sm text-slate-600 dark:text-slate-400 mb-6">
      Ricevi una notifica quando appare un nuovo articolo su un argomento,
      brand o personaggio che ti interessa.
    </p>

    <!-- Add new alert -->
    <section class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-4 mb-6">
      <label for="alert-search" class="block text-sm font-medium mb-2">
        Aggiungi un alert
      </label>
      <div class="relative" v-click-outside="closeDropdown">
        <input
          id="alert-search"
          v-model="query"
          type="text"
          placeholder="Cerca un topic (es. Samsung Galaxy, Meloni, Bitcoin)…"
          class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
          @focus="open = true"
          @input="onInput"
          @keydown.escape="closeDropdown"
        />
        <div
          v-if="open && suggestions.length"
          class="absolute z-20 left-0 right-0 top-full mt-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md shadow-lg max-h-72 overflow-y-auto"
        >
          <button
            v-for="t in suggestions"
            :key="t.id"
            type="button"
            class="w-full text-left px-3 py-2 text-sm hover:bg-slate-100 dark:hover:bg-slate-700 flex items-center justify-between"
            :disabled="hasAlertFor(t.id)"
            :class="{ 'opacity-50 cursor-not-allowed': hasAlertFor(t.id) }"
            @click="onPick(t)"
          >
            <span class="text-slate-900 dark:text-slate-100 truncate">{{ t.display_name }}</span>
            <span class="flex items-center gap-2 flex-shrink-0">
              <span :class="['text-[0.65rem] px-1.5 py-0.5 rounded-full border', topicColor(t.type)]">
                {{ t.type }}
              </span>
              <span v-if="hasAlertFor(t.id)" class="text-[0.65rem] text-slate-500">attivo</span>
            </span>
          </button>
        </div>
        <p v-if="open && query.length >= 2 && !loadingSuggest && suggestions.length === 0"
           class="absolute z-20 left-0 right-0 top-full mt-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md shadow-lg px-3 py-2 text-sm text-slate-500"
        >
          Nessun topic trovato.
        </p>
      </div>
    </section>

    <!-- List alerts -->
    <div v-if="loading" class="text-sm text-slate-500 dark:text-slate-400 py-6 text-center">
      Carico…
    </div>

    <ul v-else-if="alerts.length" class="space-y-2">
      <li
        v-for="a in alerts"
        :key="a.id"
        class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-3 flex items-center gap-3"
      >
        <label class="relative inline-flex items-center cursor-pointer">
          <input
            type="checkbox"
            :checked="a.is_enabled"
            class="sr-only peer"
            @change="onToggle(a)"
          />
          <span
            class="w-9 h-5 rounded-full bg-slate-300 dark:bg-slate-600 peer-checked:bg-blue-600 relative transition-colors"
          >
            <span
              class="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform"
              :class="{ 'translate-x-4': a.is_enabled }"
            ></span>
          </span>
        </label>

        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="font-medium text-slate-900 dark:text-slate-100 truncate">
              {{ a.topic.display_name }}
            </span>
            <span :class="['text-[0.65rem] px-1.5 py-0.5 rounded-full border', topicColor(a.topic.type)]">
              {{ a.topic.type }}
            </span>
          </div>
          <div class="flex items-center gap-3 mt-1 text-xs text-slate-500 dark:text-slate-400">
            <label class="inline-flex items-center gap-1 cursor-pointer">
              <input
                type="checkbox"
                :checked="a.channels.includes('inapp')"
                @change="onToggleChannel(a, 'inapp')"
              />
              <span>in-app</span>
            </label>
            <label class="inline-flex items-center gap-1 cursor-pointer">
              <input
                type="checkbox"
                :checked="a.channels.includes('push')"
                @change="onToggleChannel(a, 'push')"
              />
              <span>push</span>
            </label>
          </div>
        </div>

        <button
          type="button"
          class="text-xs text-red-600 dark:text-red-400 hover:underline"
          @click="onDelete(a)"
        >
          Elimina
        </button>
      </li>
    </ul>

    <p v-else class="text-sm text-slate-500 dark:text-slate-400 py-10 text-center">
      Nessun alert configurato. Aggiungine uno dal campo di ricerca qui sopra.
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, type DirectiveBinding } from "vue";
import {
  createAlert,
  deleteAlert,
  listAlerts,
  updateAlert,
} from "@/services/alerts";
import { suggest as suggestApi } from "@/services/search";
import { useToastsStore } from "@/stores/toasts";
import { extractError } from "@/services/api";
import type { AlertOut, SuggestTopicItem } from "@/types/api";

const toasts = useToastsStore();

const alerts = ref<AlertOut[]>([]);
const loading = ref(true);
const query = ref("");
const open = ref(false);
const suggestions = ref<SuggestTopicItem[]>([]);
const loadingSuggest = ref(false);

const alertTopicIds = computed(() => new Set(alerts.value.map((a) => a.topic.id)));
function hasAlertFor(topicId: number): boolean {
  return alertTopicIds.value.has(topicId);
}

let debounceTimer: number | null = null;
function onInput() {
  open.value = true;
  if (debounceTimer) window.clearTimeout(debounceTimer);
  debounceTimer = window.setTimeout(loadSuggestions, 250);
}

async function loadSuggestions() {
  const q = query.value.trim();
  if (q.length < 2) {
    suggestions.value = [];
    return;
  }
  loadingSuggest.value = true;
  try {
    const res = await suggestApi(q, 10);
    suggestions.value = res.topics;
  } catch {
    suggestions.value = [];
  } finally {
    loadingSuggest.value = false;
  }
}

function closeDropdown() {
  open.value = false;
}

async function load() {
  loading.value = true;
  try {
    alerts.value = await listAlerts();
  } finally {
    loading.value = false;
  }
}

async function onPick(topic: SuggestTopicItem) {
  if (hasAlertFor(topic.id)) return;
  try {
    const created = await createAlert(topic.id);
    // Replace existing or prepend
    const idx = alerts.value.findIndex((a) => a.id === created.id);
    if (idx >= 0) alerts.value[idx] = created;
    else alerts.value.unshift(created);
    toasts.success(`Alert attivato su «${topic.display_name}»`);
    query.value = "";
    suggestions.value = [];
    open.value = false;
  } catch (err) {
    const apiErr = await extractError(err);
    toasts.error(apiErr?.message ?? "Impossibile creare l'alert.");
  }
}

async function onToggle(a: AlertOut) {
  try {
    const updated = await updateAlert(a.id, { is_enabled: !a.is_enabled });
    const idx = alerts.value.findIndex((x) => x.id === a.id);
    if (idx >= 0) alerts.value[idx] = updated;
  } catch {
    toasts.error("Impossibile aggiornare l'alert.");
  }
}

async function onToggleChannel(a: AlertOut, channel: string) {
  const has = a.channels.includes(channel);
  const next = has
    ? a.channels.filter((c) => c !== channel)
    : [...a.channels, channel];
  // 'inapp' deve sempre rimanere se rimuovi push? No, lasciamo all'utente la
  // libertà — l'alert resta valido se almeno un canale è attivo. UX-wise
  // ricaviamo "alert silenzioso" come stato legittimo se vuota.
  try {
    const updated = await updateAlert(a.id, { channels: next });
    const idx = alerts.value.findIndex((x) => x.id === a.id);
    if (idx >= 0) alerts.value[idx] = updated;
  } catch {
    toasts.error("Impossibile aggiornare i canali.");
  }
}

async function onDelete(a: AlertOut) {
  if (!window.confirm(`Eliminare l'alert su «${a.topic.display_name}»?`)) return;
  try {
    await deleteAlert(a.id);
    alerts.value = alerts.value.filter((x) => x.id !== a.id);
    toasts.success("Alert eliminato.");
  } catch {
    toasts.error("Impossibile eliminare l'alert.");
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

// click-outside locale (no plugin)
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

onMounted(load);
</script>
