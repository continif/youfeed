<template>
  <div class="max-w-sm mx-auto px-4 py-12">
    <h1 class="text-2xl font-semibold mb-3">Controlla la tua email</h1>
    <p class="text-slate-600 dark:text-slate-400 mb-6">
      Ti abbiamo inviato un link di verifica
      <strong v-if="email">a <code>{{ email }}</code></strong
      >. Clicca sul link per attivare l'account.
    </p>

    <div class="border-t border-slate-200 dark:border-slate-700 pt-6">
      <p class="text-sm text-slate-600 dark:text-slate-400 mb-3">
        Non hai ricevuto l'email?
      </p>

      <form class="space-y-3" novalidate @submit.prevent="onResend">
        <input
          v-model="resendEmail"
          type="email"
          required
          placeholder="indirizzo email"
          class="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2"
        />
        <button
          type="submit"
          :disabled="loading"
          class="w-full rounded-md bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 disabled:opacity-50"
        >
          {{ loading ? "Invio…" : "Reinvia email di verifica" }}
        </button>
      </form>
    </div>

    <p class="mt-6 text-sm text-center">
      <RouterLink to="/login" class="text-blue-600 hover:underline">Torna al login</RouterLink>
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { resendVerification } from "@/services/auth";
import { useToastsStore } from "@/stores/toasts";
import { extractError } from "@/services/api";

const route = useRoute();
const toasts = useToastsStore();

const email = ((route.query.email as string) || "").trim();
const resendEmail = ref(email);
const loading = ref(false);

async function onResend() {
  if (!resendEmail.value) return;
  loading.value = true;
  try {
    await resendVerification(resendEmail.value);
    toasts.success("Email di verifica reinviata. Controlla la casella.");
  } catch (err) {
    const apiErr = await extractError(err);
    // Per privacy il backend ritorna 200 anche se l'email non esiste:
    // qui mostriamo sempre messaggio neutro.
    toasts.info(apiErr?.message ?? "Se l'email è registrata, riceverai il link a breve.");
  } finally {
    loading.value = false;
  }
}
</script>
