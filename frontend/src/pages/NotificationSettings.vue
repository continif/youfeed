<template>
  <div class="max-w-2xl">
    <h1 class="text-2xl font-semibold mb-2">Notifiche</h1>
    <p class="text-sm text-slate-600 dark:text-slate-400 mb-6">
      Gestisci le notifiche push del browser e i canali per gli
      <RouterLink to="/me/alerts" class="text-blue-600 hover:underline">alert</RouterLink>.
    </p>

    <section class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-5 mb-6">
      <h2 class="font-semibold mb-3">Push notifications</h2>

      <div v-if="!supported" class="text-sm text-amber-700 dark:text-amber-400 mb-3">
        Il tuo browser non supporta le notifiche push.
      </div>

      <div v-else-if="!configured" class="text-sm text-amber-700 dark:text-amber-400 mb-3">
        Il server non è ancora configurato per il Web Push (chiavi VAPID mancanti).
        Contatta l'amministratore.
      </div>

      <div v-else>
        <p class="text-sm text-slate-700 dark:text-slate-300 mb-3">
          Stato:
          <strong v-if="state === 'on'" class="text-emerald-700 dark:text-emerald-400">
            attive su questo dispositivo
          </strong>
          <strong v-else-if="state === 'denied'" class="text-red-600 dark:text-red-400">
            bloccate dal browser
          </strong>
          <strong v-else class="text-slate-500">disattivate</strong>
        </p>

        <div class="flex gap-2 flex-wrap">
          <button
            v-if="state !== 'on'"
            type="button"
            :disabled="busy"
            class="rounded-md bg-blue-600 hover:bg-blue-700 text-white font-medium px-4 py-2 disabled:opacity-50"
            @click="onSubscribe"
          >
            {{ busy ? "Attivo…" : "Attiva notifiche su questo dispositivo" }}
          </button>
          <template v-else>
            <button
              type="button"
              :disabled="busy"
              class="rounded-md border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700 px-4 py-2"
              @click="onTest"
            >
              {{ busy ? "Invio…" : "Invia notifica di test" }}
            </button>
            <button
              type="button"
              :disabled="busy"
              class="rounded-md border border-red-300 dark:border-red-700 text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 px-4 py-2"
              @click="onUnsubscribe"
            >
              Disattiva
            </button>
          </template>
        </div>

        <p class="text-xs text-slate-500 dark:text-slate-400 mt-3">
          Le notifiche push si configurano per dispositivo. Se accedi da un altro
          browser, dovrai riattivarle separatamente.
        </p>
      </div>
    </section>

    <section v-if="subscriptions.length" class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-5">
      <h2 class="font-semibold mb-3">Dispositivi registrati ({{ subscriptions.length }})</h2>
      <ul class="space-y-2 text-sm">
        <li
          v-for="s in subscriptions"
          :key="s.id"
          class="flex items-start justify-between gap-3 border border-slate-100 dark:border-slate-700 rounded p-2"
        >
          <div class="flex-1 min-w-0">
            <p class="font-medium text-slate-900 dark:text-slate-100 truncate">
              {{ describeUa(s.ua) }}
            </p>
            <p class="text-xs text-slate-400 dark:text-slate-500">
              Aggiunto {{ relTime(s.created_at) }} · Ultima attività {{ relTime(s.last_seen_at) }}
            </p>
          </div>
          <button
            type="button"
            class="text-xs text-red-600 dark:text-red-400 hover:underline self-start"
            @click="onDeleteSub(s.id)"
          >
            Rimuovi
          </button>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { formatDistanceToNow, parseISO } from "date-fns";
import { it } from "date-fns/locale";
import { api } from "@/services/api";
import {
  currentSubscription,
  getVapidKey,
  listSubscriptions,
  pushSupported,
  sendTestPush,
  subscribeUser,
  unsubscribeUser,
} from "@/services/push";
import { useToastsStore } from "@/stores/toasts";
import type { PushSubscriptionOut } from "@/types/api";

const toasts = useToastsStore();

const supported = ref(false);
const configured = ref(false);
const state = ref<"off" | "on" | "denied">("off");
const busy = ref(false);
const subscriptions = ref<PushSubscriptionOut[]>([]);

async function refresh() {
  supported.value = pushSupported();
  if (!supported.value) {
    state.value = "off";
    return;
  }
  try {
    const v = await getVapidKey();
    configured.value = v.configured;
  } catch {
    configured.value = false;
  }
  if (typeof Notification !== "undefined" && Notification.permission === "denied") {
    state.value = "denied";
  } else {
    const sub = await currentSubscription();
    state.value = sub ? "on" : "off";
  }
  try {
    subscriptions.value = await listSubscriptions();
  } catch {
    subscriptions.value = [];
  }
}

async function onSubscribe() {
  busy.value = true;
  try {
    const r = await subscribeUser();
    if (r.status === "subscribed") {
      toasts.success("Notifiche attivate.");
      await refresh();
    } else if (r.status === "permission_denied") {
      state.value = "denied";
      toasts.error("Hai bloccato le notifiche. Sbloccale dalle impostazioni del browser.");
    } else if (r.status === "not_configured") {
      toasts.error("Web push non configurato sul server.");
    } else if (r.status === "unsupported") {
      toasts.error("Browser senza supporto Web Push.");
    } else {
      toasts.error(r.message);
    }
  } finally {
    busy.value = false;
  }
}

async function onUnsubscribe() {
  busy.value = true;
  try {
    await unsubscribeUser();
    toasts.success("Notifiche disattivate.");
    await refresh();
  } finally {
    busy.value = false;
  }
}

async function onTest() {
  busy.value = true;
  try {
    await sendTestPush();
    toasts.success("Push di test inviata.");
  } catch {
    toasts.error("Impossibile inviare la push di test.");
  } finally {
    busy.value = false;
  }
}

async function onDeleteSub(id: number) {
  if (!window.confirm("Rimuovere questo dispositivo dalle notifiche push?")) return;
  try {
    await api.delete(`yf_me/push/subscriptions/${id}`);
    await refresh();
    toasts.success("Dispositivo rimosso.");
  } catch {
    toasts.error("Impossibile rimuovere il dispositivo.");
  }
}

function describeUa(ua: string | null): string {
  if (!ua) return "Dispositivo sconosciuto";
  const b = ua.match(/(Edg|Chrome|Firefox|Safari|Opera)\/(\d+)/i);
  const o = ua.match(/(Windows NT [\d.]+|Mac OS X [\d_.]+|Android [\d.]+|iPhone OS [\d_.]+|Linux)/);
  const browser = b ? b[1] : ua.split("/")[0];
  const os = o ? o[1].replace(/_/g, ".").replace(/Mac OS X/, "macOS") : "";
  return os ? `${browser} su ${os}` : browser;
}

function relTime(iso: string): string {
  try {
    return formatDistanceToNow(parseISO(iso), { addSuffix: true, locale: it });
  } catch {
    return "";
  }
}

onMounted(refresh);
</script>
