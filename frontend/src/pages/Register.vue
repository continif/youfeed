<template>
  <div class="max-w-sm mx-auto px-4 py-12">
    <h1 class="text-2xl font-semibold mb-6">Crea il tuo account</h1>

    <div class="mb-6">
      <GoogleLoginButton />
      <div class="flex items-center gap-3 my-5 text-xs text-slate-500 dark:text-slate-400">
        <span class="flex-1 h-px bg-slate-200 dark:bg-slate-700"></span>
        <span>oppure</span>
        <span class="flex-1 h-px bg-slate-200 dark:bg-slate-700"></span>
      </div>
    </div>

    <form class="space-y-4" novalidate @submit="onSubmit">
      <div>
        <label for="username" class="block text-sm font-medium">Username</label>
        <input
          id="username"
          v-model="username"
          type="text"
          autocomplete="username"
          :aria-invalid="!!usernameError"
          class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2"
          :class="{ 'border-red-500': usernameError }"
        />
        <p v-if="usernameError" class="mt-1 text-xs text-red-600 dark:text-red-400">
          {{ usernameError }}
        </p>
      </div>

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

      <div>
        <label for="password" class="block text-sm font-medium">Password</label>
        <input
          id="password"
          v-model="password"
          type="password"
          autocomplete="new-password"
          :aria-invalid="!!passwordError"
          class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2"
          :class="{ 'border-red-500': passwordError }"
        />
        <small class="text-slate-500">Almeno 10 caratteri.</small>
        <p v-if="passwordError" class="mt-1 text-xs text-red-600 dark:text-red-400">
          {{ passwordError }}
        </p>
      </div>

      <button
        type="submit"
        :disabled="isSubmitting"
        class="w-full rounded-md bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 disabled:opacity-50"
      >
        {{ isSubmitting ? "Registrazione…" : "Crea account" }}
      </button>
    </form>

    <p class="mt-6 text-sm text-slate-600 dark:text-slate-400 text-center">
      Hai già un account?
      <RouterLink to="/login" class="text-blue-600 hover:underline">Accedi</RouterLink>
    </p>
  </div>
</template>

<script setup lang="ts">
import { useForm, useField } from "vee-validate";
import { toTypedSchema } from "@vee-validate/zod";
import { RouterLink, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useToastsStore } from "@/stores/toasts";
import { extractError } from "@/services/api";
import { registerSchema } from "@/schemas/auth";
import GoogleLoginButton from "@/components/auth/GoogleLoginButton.vue";

const router = useRouter();
const auth = useAuthStore();
const toasts = useToastsStore();

const { handleSubmit, isSubmitting } = useForm({
  validationSchema: toTypedSchema(registerSchema),
  initialValues: { username: "", email: "", password: "" },
});

const { value: username, errorMessage: usernameError } = useField<string>("username");
const { value: email, errorMessage: emailError } = useField<string>("email");
const { value: password, errorMessage: passwordError } = useField<string>("password");

const onSubmit = handleSubmit(async (values) => {
  try {
    await auth.register(values.username, values.email, values.password);
    await router.push({
      name: "verify-email-pending",
      query: { email: values.email },
    });
  } catch (err) {
    const apiErr = await extractError(err);
    toasts.error(apiErr?.message ?? "Registrazione non riuscita.");
  }
});
</script>
