<template>
  <div class="min-h-screen flex flex-col items-center justify-center text-center px-4">
    <h1 class="text-6xl font-bold mb-2">404</h1>
    <p class="text-slate-500 mb-6">Pagina non trovata.</p>
    <RouterLink
      to="/"
      class="px-4 py-2 rounded-md border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
      >Torna alla home</RouterLink
    >
  </div>
</template>

<script setup lang="ts">
import { RouterLink } from "vue-router";
</script>
