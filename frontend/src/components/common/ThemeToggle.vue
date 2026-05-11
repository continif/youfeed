<template>
  <button
    type="button"
    class="w-9 h-9 rounded-full border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-center"
    :aria-label="dark ? 'Tema chiaro' : 'Tema scuro'"
    @click="toggle"
  >
    <span aria-hidden="true">{{ dark ? "☀" : "☾" }}</span>
  </button>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";

const dark = ref(false);

function applyTheme(value: boolean) {
  dark.value = value;
  document.documentElement.classList.toggle("dark", value);
  try {
    localStorage.setItem("yf_theme", value ? "dark" : "light");
  } catch {
    /* ignore */
  }
}

onMounted(() => {
  dark.value = document.documentElement.classList.contains("dark");
});

function toggle() {
  applyTheme(!dark.value);
}
</script>
