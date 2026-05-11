<template>
  <div class="max-w-sm mx-auto px-4 py-12">
    <h1 class="text-2xl font-semibold mb-6">Accedi a YouFeed</h1>

    <div class="mb-6">
      <GoogleLoginButton :next="nextPath" />
      <div class="flex items-center gap-3 my-5 text-xs text-slate-500 dark:text-slate-400">
        <span class="flex-1 h-px bg-slate-200 dark:bg-slate-700"></span>
        <span>oppure</span>
        <span class="flex-1 h-px bg-slate-200 dark:bg-slate-700"></span>
      </div>
    </div>

    <form class="space-y-4" novalidate @submit="onSubmit">
      <div>
        <label for="identifier" class="block text-sm font-medium">Username o email</label>
        <input
          id="identifier"
          v-model="identifier"
          type="text"
          autocomplete="username"
          :aria-invalid="!!identifierError"
          class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2"
          :class="{ 'border-red-500': identifierError }"
        />
        <p v-if="identifierError" class="mt-1 text-xs text-red-600 dark:text-red-400">
          {{ identifierError }}
        </p>
      </div>

      <div>
        <label for="password" class="block text-sm font-medium">Password</label>
        <input
          id="password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          :aria-invalid="!!passwordError"
          class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2"
          :class="{ 'border-red-500': passwordError }"
        />
        <p v-if="passwordError" class="mt-1 text-xs text-red-600 dark:text-red-400">
          {{ passwordError }}
        </p>
      </div>

      <button
        type="submit"
        :disabled="isSubmitting"
        class="w-full rounded-md bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 disabled:opacity-50"
      >
        {{ isSubmitting ? "Accesso in corso…" : "Accedi" }}
      </button>

      <p class="text-sm text-center">
        <RouterLink to="/forgot-password" class="text-slate-600 dark:text-slate-400 hover:text-blue-600 hover:underline">
          Password dimenticata?
        </RouterLink>
      </p>
    </form>

    <p class="mt-6 text-sm text-slate-600 dark:text-slate-400 text-center">
      Non hai un account?
      <RouterLink to="/register" class="text-blue-600 hover:underline">Registrati</RouterLink>
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useForm, useField } from "vee-validate";
import { toTypedSchema } from "@vee-validate/zod";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useToastsStore } from "@/stores/toasts";
import { extractError } from "@/services/api";
import { loginSchema } from "@/schemas/auth";
import GoogleLoginButton from "@/components/auth/GoogleLoginButton.vue";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const toasts = useToastsStore();

const nextPath = computed<string>(() => {
  const q = route.query.next;
  return typeof q === "string" && q.startsWith("/") && !q.startsWith("//")
    ? q
    : "/me/feed";
});

const { handleSubmit, isSubmitting } = useForm({
  validationSchema: toTypedSchema(loginSchema),
  initialValues: { identifier: "", password: "" },
});

const { value: identifier, errorMessage: identifierError } = useField<string>("identifier");
const { value: password, errorMessage: passwordError } = useField<string>("password");

const onSubmit = handleSubmit(async (values) => {
  try {
    await auth.login(values.identifier, values.password);
    toasts.success("Bentornato/a!");
    const next = (route.query.next as string) || "/me/feed";
    await router.push(next);
  } catch (err) {
    const apiErr = await extractError(err);
    toasts.error(apiErr?.message ?? "Accesso non riuscito.");
  }
});
</script>
