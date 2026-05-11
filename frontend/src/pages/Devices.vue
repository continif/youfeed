<template>
  <div class="max-w-2xl">
    <h1 class="text-2xl font-semibold mb-2">Dispositivi connessi</h1>
    <p class="text-sm text-slate-600 dark:text-slate-400 mb-6">
      Sessioni attualmente attive sul tuo account. Revoca quelle che non riconosci.
    </p>

    <div v-if="loading" class="text-sm text-slate-500 dark:text-slate-400 py-6 text-center">
      Carico…
    </div>

    <div v-else-if="error" class="text-sm text-red-600 dark:text-red-400 py-6 text-center">
      Errore nel caricamento. {{ error }}
    </div>

    <ul v-else-if="devices.length" class="space-y-3">
      <li
        v-for="d in devices"
        :key="d.id"
        class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-4 flex items-start gap-3"
        :class="{ 'border-blue-400 dark:border-blue-600': d.current }"
      >
        <div class="text-slate-400 dark:text-slate-500 mt-0.5">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2" stroke-linecap="round"
               stroke-linejoin="round" class="w-6 h-6" aria-hidden="true">
            <rect x="3" y="4" width="18" height="12" rx="2"/>
            <line x1="8" y1="20" x2="16" y2="20"/>
            <line x1="12" y1="16" x2="12" y2="20"/>
          </svg>
        </div>

        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="font-medium text-slate-900 dark:text-slate-100">
              {{ describeUa(d.ua) }}
            </span>
            <span
              v-if="d.current"
              class="text-[0.7rem] font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300"
            >
              Questo dispositivo
            </span>
          </div>
          <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            <span v-if="d.ip">{{ d.ip }}<span v-if="d.country"> · {{ d.country }}</span> · </span>
            <span>Ultima attività: <time :datetime="d.last_seen_at">{{ relTime(d.last_seen_at) }}</time></span>
          </p>
          <p class="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
            Accesso effettuato: <time :datetime="d.created_at">{{ relTime(d.created_at) }}</time>
          </p>
        </div>

        <button
          v-if="!d.current"
          type="button"
          class="text-xs text-red-600 dark:text-red-400 hover:underline self-start"
          :disabled="revokingId === d.id"
          @click="onRevoke(d.id)"
        >
          {{ revokingId === d.id ? "Revoco…" : "Disconnetti" }}
        </button>
      </li>
    </ul>

    <p v-else class="text-sm text-slate-500 dark:text-slate-400 py-6 text-center">
      Nessuna sessione attiva.
    </p>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { formatDistanceToNow, parseISO } from "date-fns";
import { it } from "date-fns/locale";
import { listDevices, revokeDevice } from "@/services/me";
import { useToastsStore } from "@/stores/toasts";
import { extractError } from "@/services/api";
import type { DeviceOut } from "@/types/api";

const toasts = useToastsStore();
const devices = ref<DeviceOut[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);
const revokingId = ref<string | null>(null);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    devices.value = await listDevices();
  } catch (e) {
    const apiErr = await extractError(e);
    error.value = apiErr?.message ?? String((e as Error).message ?? e);
  } finally {
    loading.value = false;
  }
}

async function onRevoke(id: string) {
  if (!window.confirm("Disconnettere questo dispositivo?")) return;
  revokingId.value = id;
  try {
    await revokeDevice(id);
    toasts.success("Dispositivo disconnesso.");
    devices.value = devices.value.filter((d) => d.id !== id);
  } catch (e) {
    const apiErr = await extractError(e);
    toasts.error(apiErr?.message ?? "Impossibile disconnettere il dispositivo.");
  } finally {
    revokingId.value = null;
  }
}

function describeUa(ua: string | null): string {
  if (!ua) return "Dispositivo sconosciuto";
  // Estrazione euristica: prima cerca browser noti, poi OS
  const browserMatch = ua.match(/(Edg|Chrome|Firefox|Safari|Opera|Brave)\/(\d+)/i);
  const osMatch = ua.match(/(Windows NT [\d.]+|Mac OS X [\d_.]+|Android [\d.]+|iPhone OS [\d_.]+|Linux)/);
  const browser = browserMatch ? `${browserMatch[1]}` : ua.split("/")[0];
  const os = osMatch ? osMatch[1].replace(/_/g, ".").replace(/Mac OS X/, "macOS") : "";
  return os ? `${browser} su ${os}` : browser;
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
