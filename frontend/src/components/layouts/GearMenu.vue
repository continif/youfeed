<template>
  <div ref="rootEl" class="relative">
    <button
      type="button"
      class="w-9 h-9 rounded-full border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-center"
      :aria-label="open ? 'Chiudi menu' : 'Apri menu impostazioni'"
      :aria-expanded="open"
      aria-haspopup="menu"
      @click="open = !open"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        class="w-5 h-5"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="3" />
        <path
          d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.01a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.01a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"
        />
      </svg>
    </button>

    <div
      v-if="open"
      role="menu"
      class="absolute right-0 mt-2 w-56 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-lg z-30 py-1 text-sm"
    >
      <RouterLink
        v-for="link in navLinks"
        :key="link.to"
        :to="link.to"
        role="menuitem"
        class="block px-4 py-2 hover:bg-slate-100 dark:hover:bg-slate-700"
        @click="open = false"
        >{{ link.label }}</RouterLink
      >
      <hr class="my-1 border-slate-200 dark:border-slate-700" />
      <button
        type="button"
        role="menuitem"
        class="w-full text-left px-4 py-2 hover:bg-slate-100 dark:hover:bg-slate-700 flex items-center gap-2"
        @click="toggleTheme"
      >
        <span aria-hidden="true">{{ dark ? "☀" : "☾" }}</span>
        <span>{{ dark ? "Tema chiaro" : "Tema scuro" }}</span>
      </button>
      <hr class="my-1 border-slate-200 dark:border-slate-700" />
      <button
        v-if="auth.user"
        type="button"
        role="menuitem"
        class="w-full text-left px-4 py-2 hover:bg-slate-100 dark:hover:bg-slate-700 text-red-600 dark:text-red-400"
        @click="onLogout"
      >
        Esci
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useClickOutside } from "@/composables/useClickOutside";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const open = ref(false);
const rootEl = ref<HTMLElement | null>(null);
const dark = ref(false);

const navLinks = [
  { to: "/me/sources", label: "Fonti" },
  { to: "/me/categories", label: "Categorie" },
  { to: "/me/alerts", label: "Alert" },
  { to: "/me/settings/account", label: "Impostazioni" },
  { to: "/me/settings/notifications", label: "Notifiche" },
  { to: "/me/settings/devices", label: "Dispositivi" },
  { to: "/me/settings/aspect", label: "Aspetto" },
];

useClickOutside(rootEl, () => {
  open.value = false;
});

watch(
  () => route.fullPath,
  () => {
    open.value = false;
  },
);

onMounted(() => {
  dark.value = document.documentElement.classList.contains("dark");
});

function toggleTheme() {
  dark.value = !dark.value;
  document.documentElement.classList.toggle("dark", dark.value);
  try {
    localStorage.setItem("yf_theme", dark.value ? "dark" : "light");
  } catch {
    /* ignore */
  }
}

async function onLogout() {
  open.value = false;
  await auth.logout();
  await router.push({ name: "login" });
}
</script>
