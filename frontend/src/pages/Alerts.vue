<template>
  <div class="max-w-2xl">
    <h1 class="text-2xl font-semibold mb-2">Alert</h1>
    <p class="text-sm text-slate-600 dark:text-slate-400 mb-6">
      Ricevi notifiche quando un articolo combina i topic che ti interessano.
      Puoi mettere più topic in un singolo alert e scegliere se devono essere
      tutti presenti (AND) o se ne basta uno (OR).
    </p>

    <!-- Build new alert -->
    <section class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-4 mb-6">
      <h2 class="font-semibold text-sm mb-2">Crea nuovo alert</h2>

      <!-- Topic search input -->
      <div class="relative" v-click-outside="closeDropdown">
        <input
          v-model="query"
          type="text"
          placeholder="Cerca topic da aggiungere (es. Samsung, Meloni, Bitcoin)…"
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
            :disabled="isPicked(t.id)"
            :class="{ 'opacity-50 cursor-not-allowed': isPicked(t.id) }"
            @click="addPick(t)"
          >
            <span class="text-slate-900 dark:text-slate-100 truncate">{{ t.display_name }}</span>
            <span class="flex items-center gap-2 flex-shrink-0">
              <span :class="['text-[0.65rem] px-1.5 py-0.5 rounded-full border', topicColor(t.type)]">
                {{ t.type }}
              </span>
              <span v-if="isPicked(t.id)" class="text-[0.65rem] text-slate-500">aggiunto</span>
            </span>
          </button>
        </div>
        <p v-if="open && query.length >= 2 && !loadingSuggest && suggestions.length === 0"
           class="absolute z-20 left-0 right-0 top-full mt-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md shadow-lg px-3 py-2 text-sm text-slate-500"
        >
          Nessun topic trovato.
        </p>
      </div>

      <!-- Selected topics (chips) -->
      <div v-if="picks.length" class="mt-3 flex flex-wrap gap-1.5">
        <span
          v-for="p in picks"
          :key="p.id"
          :class="['inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-full border', topicColor(p.type)]"
        >
          <span>{{ p.display_name }}</span>
          <button
            type="button"
            class="font-bold text-slate-600 hover:text-red-600"
            aria-label="Rimuovi"
            @click="removePick(p.id)"
          >×</button>
        </span>
      </div>

      <!-- Match mode + create -->
      <div v-if="picks.length" class="mt-3 flex items-center justify-between gap-3 flex-wrap">
        <div class="flex items-center gap-3 text-sm text-slate-700 dark:text-slate-300">
          <label class="inline-flex items-center gap-1 cursor-pointer">
            <input type="radio" v-model="matchMode" value="all" />
            <span>Tutti (AND)</span>
          </label>
          <label class="inline-flex items-center gap-1 cursor-pointer">
            <input type="radio" v-model="matchMode" value="any" />
            <span>Almeno uno (OR)</span>
          </label>
        </div>
        <button
          type="button"
          class="rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-1.5 disabled:opacity-50"
          :disabled="creating || picks.length === 0"
          @click="onCreate"
        >
          {{ creating ? "Creo…" : `Crea alert (${picks.length} topic)` }}
        </button>
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
        class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-3"
      >
        <div class="flex items-start gap-3">
          <label class="relative inline-flex items-center cursor-pointer mt-1 flex-shrink-0">
            <input type="checkbox" :checked="a.is_enabled" class="sr-only peer" @change="onToggleEnabled(a)" />
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
            <div class="flex items-center gap-2 flex-wrap">
              <span class="text-[0.7rem] uppercase font-semibold px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300">
                {{ a.match_mode === "all" ? "Tutti" : "Almeno uno" }}
              </span>
              <span
                v-for="t in a.topics"
                :key="t.id"
                :class="['text-[0.7rem] px-2 py-0.5 rounded-full border', topicColor(t.type)]"
              >
                {{ t.display_name }}
              </span>
            </div>
            <div class="flex items-center gap-3 mt-1.5 text-xs text-slate-500 dark:text-slate-400">
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
            class="text-xs text-red-600 dark:text-red-400 hover:underline self-start"
            @click="onDelete(a)"
          >
            Elimina
          </button>
        </div>
      </li>
    </ul>

    <p v-else class="text-sm text-slate-500 dark:text-slate-400 py-10 text-center">
      Nessun alert configurato. Aggiungi qualche topic qui sopra e crea il tuo primo alert.
    </p>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, type DirectiveBinding } from "vue";
import { useRouter } from "vue-router";
import {
  createAlert,
  deleteAlert,
  listAlerts,
  updateAlert,
} from "@/services/alerts";
import { currentSubscription, pushSupported } from "@/services/push";
import { suggest as suggestApi } from "@/services/search";
import { useToastsStore } from "@/stores/toasts";
import { extractError } from "@/services/api";
import type { AlertMatchMode, AlertOut, AlertTopicOut, SuggestTopicItem } from "@/types/api";

const toasts = useToastsStore();
const router = useRouter();

const alerts = ref<AlertOut[]>([]);
const loading = ref(true);

// Composer state
const query = ref("");
const open = ref(false);
const suggestions = ref<SuggestTopicItem[]>([]);
const loadingSuggest = ref(false);
const picks = ref<AlertTopicOut[]>([]);
const matchMode = ref<AlertMatchMode>("all");
const creating = ref(false);

function isPicked(id: number): boolean {
  return picks.value.some((p) => p.id === id);
}

function addPick(t: SuggestTopicItem) {
  if (isPicked(t.id)) return;
  if (picks.value.length >= 10) {
    toasts.error("Massimo 10 topic per alert.");
    return;
  }
  picks.value.push({ id: t.id, slug: t.slug, display_name: t.display_name, type: t.type });
  query.value = "";
  suggestions.value = [];
  open.value = false;
}

function removePick(id: number) {
  picks.value = picks.value.filter((p) => p.id !== id);
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

async function onCreate() {
  if (!picks.value.length) return;
  creating.value = true;
  try {
    const created = await createAlert(
      picks.value.map((p) => p.id),
      { matchMode: matchMode.value },
    );
    alerts.value.unshift(created);
    const labels = picks.value.map((p) => p.display_name).join(" + ");
    toasts.success(`Alert creato su «${labels}»`);
    picks.value = [];
    matchMode.value = "all";
  } catch (err) {
    const apiErr = await extractError(err);
    toasts.error(apiErr?.message ?? "Impossibile creare l'alert.");
  } finally {
    creating.value = false;
  }
}

async function onToggleEnabled(a: AlertOut) {
  try {
    const updated = await updateAlert(a.id, { is_enabled: !a.is_enabled });
    const idx = alerts.value.findIndex((x) => x.id === a.id);
    if (idx >= 0) alerts.value[idx] = updated;
  } catch {
    toasts.error("Impossibile aggiornare l'alert.");
  }
}

async function pushReadyOnThisDevice(): Promise<boolean> {
  if (!pushSupported()) return false;
  if (typeof Notification !== "undefined" && Notification.permission !== "granted") {
    return false;
  }
  const sub = await currentSubscription();
  return sub !== null;
}

async function onToggleChannel(a: AlertOut, channel: string) {
  const has = a.channels.includes(channel);
  const next = has
    ? a.channels.filter((c) => c !== channel)
    : [...a.channels, channel];

  // Se sta accendendo "push" ma il browser non è subscribed, glielo dice e
  // lo offre il link diretto. Il canale viene comunque salvato come
  // preferenza: se in futuro attiva le push da un device, l'alert le riceve.
  if (!has && channel === "push" && !(await pushReadyOnThisDevice())) {
    const goNow = window.confirm(
      "Per ricevere notifiche push devi prima attivarle in questo browser.\n\n" +
        "Vuoi andare ora alla pagina per attivarle?",
    );
    if (goNow) {
      await router.push("/me/settings/notifications");
      return;
    }
    toasts.info("Canale push salvato come preferenza, ma non riceverai notifiche finché non le attivi.");
  }

  try {
    const updated = await updateAlert(a.id, { channels: next });
    const idx = alerts.value.findIndex((x) => x.id === a.id);
    if (idx >= 0) alerts.value[idx] = updated;
  } catch {
    toasts.error("Impossibile aggiornare i canali.");
  }
}

async function onDelete(a: AlertOut) {
  const label = a.topics.map((t) => t.display_name).join(" + ");
  if (!window.confirm(`Eliminare l'alert su «${label}»?`)) return;
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
