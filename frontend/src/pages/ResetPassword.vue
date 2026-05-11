<template>
  <div class="max-w-sm mx-auto px-4 py-12">
    <h1 class="text-2xl font-semibold mb-2">Imposta una nuova password</h1>
    <p v-if="!done" class="text-sm text-slate-600 dark:text-slate-400 mb-6">
      Scegli una nuova password (almeno 10 caratteri).
    </p>

    <div v-if="!token" class="rounded-md border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/30 text-red-900 dark:text-red-200 px-4 py-3 text-sm">
      Link non valido. Torna alla
      <RouterLink to="/forgot-password" class="underline">pagina di reset</RouterLink>
      per richiederne uno nuovo.
    </div>

    <div
      v-else-if="done"
      class="rounded-md border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/30 text-emerald-900 dark:text-emerald-200 px-4 py-3 text-sm"
    >
      <p class="font-medium mb-1">Password aggiornata.</p>
      <p>
        Ora puoi
        <RouterLink to="/login" class="text-emerald-700 dark:text-emerald-300 underline">
          accedere con la nuova password
        </RouterLink>.
      </p>
    </div>

    <form v-else class="space-y-4" novalidate @submit="onSubmit">
      <div>
        <label for="new_password" class="block text-sm font-medium">Nuova password</label>
        <input
          id="new_password"
          v-model="newPassword"
          type="password"
          autocomplete="new-password"
          :aria-invalid="!!newPasswordError"
          class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2"
          :class="{ 'border-red-500': newPasswordError }"
        />
        <small class="text-slate-500">Almeno 10 caratteri.</small>
        <p v-if="newPasswordError" class="mt-1 text-xs text-red-600 dark:text-red-400">
          {{ newPasswordError }}
        </p>
      </div>

      <div>
        <label for="confirm_password" class="block text-sm font-medium">Conferma password</label>
        <input
          id="confirm_password"
          v-model="confirmPassword"
          type="password"
          autocomplete="new-password"
          :aria-invalid="!!confirmPasswordError"
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
        class="w-full rounded-md bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 disabled:opacity-50"
      >
        {{ isSubmitting ? "Aggiornamento…" : "Imposta nuova password" }}
      </button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useForm, useField } from "vee-validate";
import { toTypedSchema } from "@vee-validate/zod";
import { RouterLink, useRoute } from "vue-router";
import { useToastsStore } from "@/stores/toasts";
import { extractError } from "@/services/api";
import { resetPassword } from "@/services/auth";
import { resetPasswordSchema } from "@/schemas/auth";

const route = useRoute();
const toasts = useToastsStore();
const done = ref(false);

const token = computed<string>(() => {
  const t = route.query.token;
  return typeof t === "string" ? t : "";
});

const { handleSubmit, isSubmitting } = useForm({
  validationSchema: toTypedSchema(resetPasswordSchema),
  initialValues: { new_password: "", confirm_password: "" },
});

const { value: newPassword, errorMessage: newPasswordError } =
  useField<string>("new_password");
const { value: confirmPassword, errorMessage: confirmPasswordError } =
  useField<string>("confirm_password");

const onSubmit = handleSubmit(async (values) => {
  if (!token.value) return;
  try {
    await resetPassword(token.value, values.new_password);
    done.value = true;
  } catch (err) {
    const apiErr = await extractError(err);
    toasts.error(apiErr?.message ?? "Impossibile aggiornare la password.");
  }
});
</script>
