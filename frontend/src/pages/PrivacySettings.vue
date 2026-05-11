<template>
  <div class="max-w-xl">
    <h1 class="text-2xl font-semibold mb-6">Privacy</h1>

    <!-- Tracking consent -->
    <section class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-6 mb-6">
      <h2 class="font-semibold mb-2">Analisi di lettura</h2>
      <p class="text-sm text-slate-600 dark:text-slate-400 mb-4">
        Per migliorare i tuoi suggerimenti, registriamo quali articoli leggi e per quanto tempo.
        Senza il consenso, queste statistiche non vengono raccolte e non viene generato
        nessun fingerprint del tuo browser.
      </p>

      <div class="flex items-center gap-3 mb-2">
        <span
          :class="[
            'inline-block w-3 h-3 rounded-full',
            consent === 'granted'
              ? 'bg-emerald-500'
              : consent === 'denied'
                ? 'bg-red-500'
                : 'bg-slate-400',
          ]"
        />
        <span class="text-sm">
          Stato attuale:
          <strong>
            {{
              consent === "granted"
                ? "Consenso accordato"
                : consent === "denied"
                  ? "Tracciamento disattivato"
                  : "Da decidere"
            }}
          </strong>
        </span>
      </div>

      <div class="flex gap-2 mt-3">
        <button
          v-if="consent !== 'granted'"
          type="button"
          class="rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm px-3 py-2"
          @click="onGrant"
        >
          Accetta
        </button>
        <button
          v-if="consent !== 'denied'"
          type="button"
          class="rounded-md border border-slate-300 dark:border-slate-700 text-sm px-3 py-2"
          @click="onDeny"
        >
          Rifiuta
        </button>
      </div>
    </section>

    <!-- Export GDPR -->
    <section class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-6">
      <h2 class="font-semibold mb-2">Scarica i miei dati</h2>
      <p class="text-sm text-slate-600 dark:text-slate-400 mb-3">
        Esporta in formato ZIP tutti i dati che YouFeed ha su di te:
        utente, categorie, fonti, sessioni di login.
      </p>
      <button
        type="button"
        class="rounded-md border border-slate-300 dark:border-slate-700 text-sm px-3 py-2 hover:bg-slate-100 dark:hover:bg-slate-700"
        :disabled="downloading"
        @click="onDownload"
      >
        {{ downloading ? "Preparazione…" : "Scarica export ZIP" }}
      </button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useTrackingConsent } from "@/composables/useTrackingConsent";
import { useAuthStore } from "@/stores/auth";
import { useToastsStore } from "@/stores/toasts";
import { downloadExport } from "@/services/me";
import { extractError } from "@/services/api";

const { consent, grant, deny } = useTrackingConsent();
const toasts = useToastsStore();
const auth = useAuthStore();

function onGrant() {
  grant();
  toasts.success("Consenso accordato.");
}

function onDeny() {
  deny();
  toasts.info("Tracciamento disattivato.");
}

const downloading = ref(false);
async function onDownload() {
  downloading.value = true;
  try {
    const filename = auth.user
      ? `youfeed-export-${auth.user.username}.zip`
      : "youfeed-export.zip";
    await downloadExport(filename);
    toasts.success("Download avviato.");
  } catch (err) {
    const apiErr = await extractError(err);
    toasts.error(apiErr?.message ?? "Errore durante l'export.");
  } finally {
    downloading.value = false;
  }
}
</script>
