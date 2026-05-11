<template>
  <div class="max-w-sm mx-auto px-4 py-12">
    <h1 class="text-2xl font-semibold mb-2">Password dimenticata?</h1>
    <p class="text-sm text-slate-600 dark:text-slate-400 mb-6">
      Inserisci la tua email: ti invieremo un link per impostare una nuova password.
    </p>

    <div
      v-if="submitted"
      class="rounded-md border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/30 text-emerald-900 dark:text-emerald-200 px-4 py-3 text-sm"
    >
      <p class="font-medium mb-1">Controlla la tua casella email.</p>
      <p>
        Se l'indirizzo è registrato, riceverai a breve un link per reimpostare la
        password. Il link è valido per 1 ora.
      </p>
      <p class="mt-3">
        <RouterLink to="/login" class="text-emerald-700 dark:text-emerald-300 underline">
          Torna al login
        </RouterLink>
      </p>
    </div>

    <form v-else class="space-y-4" novalidate @submit="onSubmit">
      <div>
        <label for="email" class="block text-sm font-medium">Email</label>
        <input
          id="email"
          v-model="email"
          type="email"
          autocomplete="email"
          :aria-invalid="!!emailError"
          class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2"
          :class="{ 'border-red-500': emailError }"
        />
        <p v-if="emailError" class="mt-1 text-xs text-red-600 dark:text-red-400">
          {{ emailError }}
        </p>
      </div>

      <button
        type="submit"
        :disabled="isSubmitting"
        class="w-full rounded-md bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 disabled:opacity-50"
      >
        {{ isSubmitting ? "Invio in corso…" : "Invia link di reset" }}
      </button>
    </form>

    <p class="mt-6 text-sm text-slate-600 dark:text-slate-400 text-center">
      Ti sei ricordato la password?
      <RouterLink to="/login" class="text-blue-600 hover:underline">Accedi</RouterLink>
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useForm, useField } from "vee-validate";
import { toTypedSchema } from "@vee-validate/zod";
import { RouterLink } from "vue-router";
import { useToastsStore } from "@/stores/toasts";
import { extractError } from "@/services/api";
import { forgotPassword } from "@/services/auth";
import { forgotPasswordSchema } from "@/schemas/auth";

const toasts = useToastsStore();
const submitted = ref(false);

const { handleSubmit, isSubmitting } = useForm({
  validationSchema: toTypedSchema(forgotPasswordSchema),
  initialValues: { email: "" },
});

const { value: email, errorMessage: emailError } = useField<string>("email");

const onSubmit = handleSubmit(async (values) => {
  try {
    await forgotPassword(values.email);
    submitted.value = true;
  } catch (err) {
    const apiErr = await extractError(err);
    toasts.error(apiErr?.message ?? "Impossibile inviare il link. Riprova.");
  }
});
</script>
