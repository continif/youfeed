<template>
  <div class="max-w-xl">
    <h1 class="text-2xl font-semibold mb-6">Account</h1>

    <!-- Feed RSS personale -->
    <section
      v-if="auth.user?.username"
      class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-6 mb-6"
    >
      <h2 class="font-semibold mb-2">Il tuo feed RSS</h2>
      <p class="text-sm text-slate-600 dark:text-slate-400 mb-3">
        Sottoscrivi questo URL su qualsiasi lettore RSS (Feedly, NetNewsWire,
        Thunderbird, …) per ricevere lì il tuo feed personale.
      </p>
      <div class="flex items-stretch gap-2">
        <input
          ref="rssInput"
          type="text"
          readonly
          :value="rssUrl"
          class="flex-1 min-w-0 px-3 py-2 rounded-md border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-900 text-sm font-mono"
          @focus="onRssFocus"
        />
        <button
          type="button"
          class="px-3 py-2 text-sm rounded-md bg-blue-600 hover:bg-blue-700 text-white"
          @click="onCopyRss"
        >
          {{ copied ? "Copiato" : "Copia" }}
        </button>
        <a
          :href="rssUrl"
          target="_blank"
          rel="noopener"
          class="px-3 py-2 text-sm rounded-md border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700"
        >Apri</a>
      </div>
    </section>

    <!-- Change password -->
    <section class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-6 mb-6">
      <h2 class="font-semibold mb-3">Cambia password</h2>
      <form class="space-y-3" novalidate @submit="onChangePassword">
        <div>
          <label class="block text-sm font-medium">Password attuale</label>
          <input
            v-model="currentPassword"
            type="password"
            autocomplete="current-password"
            class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2"
            :class="{ 'border-red-500': currentPasswordError }"
          />
          <p v-if="currentPasswordError" class="mt-1 text-xs text-red-600 dark:text-red-400">
            {{ currentPasswordError }}
          </p>
        </div>
        <div>
          <label class="block text-sm font-medium">Nuova password</label>
          <input
            v-model="newPassword"
            type="password"
            autocomplete="new-password"
            class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2"
            :class="{ 'border-red-500': newPasswordError }"
          />
          <p v-if="newPasswordError" class="mt-1 text-xs text-red-600 dark:text-red-400">
            {{ newPasswordError }}
          </p>
        </div>
        <div>
          <label class="block text-sm font-medium">Conferma nuova password</label>
          <input
            v-model="confirmPassword"
            type="password"
            autocomplete="new-password"
            class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2"
            :class="{ 'border-red-500': confirmPasswordError }"
          />
          <p v-if="confirmPasswordError" class="mt-1 text-xs text-red-600 dark:text-red-400">
            {{ confirmPasswordError }}
          </p>
        </div>
        <button
          type="submit"
          :disabled="isSubmitting"
          class="rounded-md bg-blue-600 hover:bg-blue-700 text-white font-medium px-4 py-2 disabled:opacity-50"
        >
          {{ isSubmitting ? "Salvataggio…" : "Aggiorna password" }}
        </button>
      </form>
    </section>

    <!-- Danger zone: delete account -->
    <section class="bg-white dark:bg-slate-800 border border-red-300 dark:border-red-900 rounded-lg p-6">
      <h2 class="font-semibold mb-2 text-red-700 dark:text-red-400">Elimina account</h2>
      <p class="text-sm text-slate-600 dark:text-slate-400 mb-3">
        Cancella definitivamente il tuo account, le categorie e l'iscrizione alle fonti.
        L'azione è irreversibile. I tuoi dati di lettura aggregati restano in forma anonima.
      </p>
      <button
        type="button"
        class="rounded-md border border-red-600 text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 px-4 py-2 text-sm"
        :disabled="deleting"
        @click="onDelete"
      >
        {{ deleting ? "Eliminazione…" : "Elimina il mio account" }}
      </button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from "vue-router";
import { useForm, useField } from "vee-validate";
import { toTypedSchema } from "@vee-validate/zod";
import { computed, ref } from "vue";
import { changePassword, deleteAccount } from "@/services/me";
import { useAuthStore } from "@/stores/auth";
import { useToastsStore } from "@/stores/toasts";
import { extractError } from "@/services/api";
import { changePasswordSchema } from "@/schemas/me";

const router = useRouter();
const auth = useAuthStore();
const toasts = useToastsStore();

// Feed RSS personale
const rssUrl = computed(() => {
  const u = auth.user?.username ?? "";
  return `${window.location.origin}/yf_users/${u}/feed.rss`;
});
const copied = ref(false);

function onRssFocus(e: FocusEvent) {
  (e.target as HTMLInputElement | null)?.select();
}

async function onCopyRss() {
  try {
    await navigator.clipboard.writeText(rssUrl.value);
    copied.value = true;
    setTimeout(() => (copied.value = false), 1500);
  } catch {
    toasts.error("Impossibile copiare. Selezionalo e usa Ctrl+C.");
  }
}

const { handleSubmit, isSubmitting, resetForm } = useForm({
  validationSchema: toTypedSchema(changePasswordSchema),
  initialValues: { current_password: "", new_password: "", confirm_password: "" },
});

const { value: currentPassword, errorMessage: currentPasswordError } = useField<string>(
  "current_password",
);
const { value: newPassword, errorMessage: newPasswordError } = useField<string>("new_password");
const { value: confirmPassword, errorMessage: confirmPasswordError } = useField<string>(
  "confirm_password",
);

const onChangePassword = handleSubmit(async (values) => {
  try {
    await changePassword(values.current_password, values.new_password);
    toasts.success("Password aggiornata.");
    resetForm();
  } catch (err) {
    const apiErr = await extractError(err);
    toasts.error(apiErr?.message ?? "Errore nell'aggiornamento.");
  }
});

const deleting = ref(false);
async function onDelete() {
  const confirmText = `ELIMINA-${auth.user?.username ?? ""}`;
  const answer = window.prompt(
    `Per confermare l'eliminazione dell'account, scrivi: ${confirmText}`,
  );
  if (answer !== confirmText) {
    toasts.info("Eliminazione annullata.");
    return;
  }
  deleting.value = true;
  try {
    await deleteAccount();
    auth.user = null; // svuota state immediato
    toasts.success("Account eliminato.");
    await router.push({ name: "login" });
  } catch (err) {
    const apiErr = await extractError(err);
    toasts.error(apiErr?.message ?? "Errore nell'eliminazione.");
  } finally {
    deleting.value = false;
  }
}
</script>
