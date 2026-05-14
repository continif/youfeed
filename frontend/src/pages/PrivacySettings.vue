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
    <section class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-6 mb-6">
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

    <!-- Cancellazione account -->
    <section class="bg-white dark:bg-slate-800 border border-red-200 dark:border-red-900 rounded-lg p-6">
      <h2 class="font-semibold mb-2 text-red-700 dark:text-red-400">Cancella account</h2>
      <p class="text-sm text-slate-600 dark:text-slate-400 mb-3">
        Rimuove permanentemente account, categorie, fonti scelte, salvati,
        alert e sessioni attive. I segnali di lettura vengono resi anonimi
        (non più riconducibili a te). Operazione <strong>non reversibile</strong>.
      </p>

      <div v-if="!confirmingDelete">
        <button
          type="button"
          class="rounded-md border border-red-300 dark:border-red-800 text-red-700 dark:text-red-400 text-sm px-3 py-2 hover:bg-red-50 dark:hover:bg-red-950"
          @click="confirmingDelete = true"
        >
          Cancella il mio account
        </button>
      </div>

      <div v-else class="space-y-3">
        <p class="text-sm">
          Per confermare, digita il tuo username <strong>{{ auth.user?.username }}</strong>:
        </p>
        <input
          v-model="deleteConfirmText"
          type="text"
          autocomplete="off"
          spellcheck="false"
          class="w-full px-3 py-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
          :placeholder="auth.user?.username"
        />
        <div class="flex gap-2">
          <button
            type="button"
            class="rounded-md bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-sm px-3 py-2"
            :disabled="deleting || deleteConfirmText !== auth.user?.username"
            @click="onDelete"
          >
            {{ deleting ? "Cancellazione…" : "Conferma cancellazione" }}
          </button>
          <button
            type="button"
            class="rounded-md border border-slate-300 dark:border-slate-700 text-sm px-3 py-2"
            :disabled="deleting"
            @click="cancelDelete"
          >
            Annulla
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useTrackingConsent } from "@/composables/useTrackingConsent";
import { useAuthStore } from "@/stores/auth";
import { useToastsStore } from "@/stores/toasts";
import { deleteAccount, downloadExport } from "@/services/me";
import { extractError } from "@/services/api";

const { consent, grant, deny } = useTrackingConsent();
const toasts = useToastsStore();
const auth = useAuthStore();
const router = useRouter();

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

const confirmingDelete = ref(false);
const deleteConfirmText = ref("");
const deleting = ref(false);

function cancelDelete() {
  confirmingDelete.value = false;
  deleteConfirmText.value = "";
}

async function onDelete() {
  if (deleteConfirmText.value !== auth.user?.username) return;
  deleting.value = true;
  try {
    await deleteAccount();
    // Lo store auth è ora stale: il backend ha cancellato il cookie sessione
    // e revocato tutto. Forziamo logout client-side e ridirezione a /.
    auth.$reset?.();
    toasts.success("Account cancellato.");
    await router.replace("/");
  } catch (err) {
    const apiErr = await extractError(err);
    toasts.error(apiErr?.message ?? "Errore durante la cancellazione.");
  } finally {
    deleting.value = false;
  }
}
</script>
