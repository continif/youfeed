<template>
  <div class="max-w-2xl">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-semibold">Notifiche</h1>
      <button
        v-if="hasUnread"
        type="button"
        class="text-sm text-blue-600 hover:underline"
        :disabled="markingAll"
        @click="onMarkAllRead"
      >
        {{ markingAll ? "Salvo…" : "Segna tutte come lette" }}
      </button>
    </div>

    <div v-if="loading" class="text-sm text-slate-500 dark:text-slate-400 py-6 text-center">
      Carico…
    </div>

    <div v-else-if="error" class="text-sm text-red-600 dark:text-red-400 py-6 text-center">
      {{ error }}
    </div>

    <ul v-else-if="items.length" class="space-y-2">
      <li
        v-for="n in items"
        :key="n.id"
        class="bg-white dark:bg-slate-800 border rounded-lg p-4 cursor-pointer transition-colors"
        :class="
          n.read_at
            ? 'border-slate-200 dark:border-slate-700'
            : 'border-blue-300 dark:border-blue-700 bg-blue-50/40 dark:bg-blue-900/10'
        "
        @click="onClick(n)"
      >
        <div class="flex items-start gap-3">
          <span
            class="mt-1 w-2 h-2 rounded-full flex-shrink-0"
            :class="n.read_at ? 'bg-slate-300 dark:bg-slate-600' : 'bg-blue-500'"
            aria-hidden="true"
          ></span>
          <div class="flex-1 min-w-0">
            <p class="font-medium text-slate-900 dark:text-slate-100">{{ n.title }}</p>
            <p v-if="n.body" class="text-sm text-slate-600 dark:text-slate-400 mt-0.5">
              {{ n.body }}
            </p>
            <p class="text-xs text-slate-400 dark:text-slate-500 mt-1">
              <time :datetime="n.created_at">{{ relTime(n.created_at) }}</time>
            </p>
          </div>
        </div>
      </li>
    </ul>

    <p v-else class="text-sm text-slate-500 dark:text-slate-400 py-10 text-center">
      Nessuna notifica al momento.
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { formatDistanceToNow, parseISO } from "date-fns";
import { it } from "date-fns/locale";
import {
  listNotifications,
  markAllRead,
  markRead,
} from "@/services/notifications";
import { useToastsStore } from "@/stores/toasts";
import { useNotificationsStore } from "@/stores/notifications";
import type { NotificationOut } from "@/types/api";

const router = useRouter();
const toasts = useToastsStore();
const notifStore = useNotificationsStore();

const items = ref<NotificationOut[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);
const markingAll = ref(false);

const hasUnread = computed(() => items.value.some((n) => !n.read_at));

async function load() {
  loading.value = true;
  error.value = null;
  try {
    items.value = await listNotifications({ limit: 100 });
  } catch (e) {
    error.value = String((e as Error).message ?? e);
  } finally {
    loading.value = false;
  }
}

async function onClick(n: NotificationOut) {
  if (!n.read_at) {
    try {
      const updated = await markRead(n.id);
      const idx = items.value.findIndex((x) => x.id === n.id);
      if (idx >= 0) items.value[idx] = updated;
      notifStore.refresh();
    } catch {
      /* non-fatal */
    }
  }
  if (n.link) {
    await router.push(n.link);
  }
}

async function onMarkAllRead() {
  markingAll.value = true;
  try {
    await markAllRead();
    const now = new Date().toISOString();
    items.value = items.value.map((n) => (n.read_at ? n : { ...n, read_at: now }));
    notifStore.refresh();
    toasts.success("Tutte le notifiche segnate come lette.");
  } catch {
    toasts.error("Impossibile aggiornare le notifiche.");
  } finally {
    markingAll.value = false;
  }
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
