<template>
  <div class="max-w-sm mx-auto px-4 py-16 text-center">
    <template v-if="state === 'loading'">
      <div class="animate-pulse">
        <div class="h-8 bg-slate-200 dark:bg-slate-700 rounded w-3/4 mx-auto mb-3"></div>
        <div class="h-4 bg-slate-200 dark:bg-slate-700 rounded w-1/2 mx-auto"></div>
      </div>
      <p class="mt-6 text-slate-500">Verifico il token…</p>
    </template>

    <template v-else-if="state === 'success'">
      <h1 class="text-2xl font-semibold text-emerald-700 dark:text-emerald-400 mb-3">
        Email verificata
      </h1>
      <p class="text-slate-600 dark:text-slate-400 mb-6">
        Ora puoi accedere al tuo account YouFeed.
      </p>
      <RouterLink
        to="/login"
        class="inline-block px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-700 text-white"
        >Vai al login</RouterLink
      >
    </template>

    <template v-else>
      <h1 class="text-2xl font-semibold text-red-700 dark:text-red-400 mb-3">
        Verifica fallita
      </h1>
      <p class="text-slate-600 dark:text-slate-400 mb-6">
        {{ errorMessage }}
      </p>
      <div class="flex flex-col gap-2">
        <RouterLink
          to="/verify-email-pending"
          class="px-4 py-2 rounded-md border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
          >Reinvia email</RouterLink
        >
        <RouterLink to="/login" class="text-sm text-blue-600 hover:underline">
          Torna al login
        </RouterLink>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { verifyEmail } from "@/services/auth";
import { extractError } from "@/services/api";

const route = useRoute();

const state = ref<"loading" | "success" | "error">("loading");
const errorMessage = ref("Token non valido o scaduto.");

onMounted(async () => {
  const token = (route.query.token as string) || "";
  if (!token) {
    state.value = "error";
    errorMessage.value = "Token mancante nella URL.";
    return;
  }
  try {
    await verifyEmail(token);
    state.value = "success";
  } catch (err) {
    const apiErr = await extractError(err);
    if (apiErr?.code === "expired_token") {
      errorMessage.value = "Il link è scaduto. Richiedi una nuova email di verifica.";
    } else if (apiErr?.code === "invalid_token") {
      errorMessage.value = "Il link non è valido. Potrebbe essere già stato usato.";
    } else if (apiErr?.message) {
      errorMessage.value = apiErr.message;
    }
    state.value = "error";
  }
});
</script>
