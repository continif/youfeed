<template>
  <div class="min-h-screen flex flex-col">
    <header class="border-b border-slate-200 dark:border-slate-700">
      <div class="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
        <RouterLink to="/" class="font-bold text-lg">YouFeed</RouterLink>
        <nav class="flex items-center gap-3 text-sm">
          <RouterLink to="/login" class="hover:underline">Accedi</RouterLink>
          <RouterLink
            to="/register"
            class="px-3 py-1.5 rounded-md bg-blue-600 text-white hover:bg-blue-700"
            >Registrati</RouterLink
          >
          <ThemeToggle />
        </nav>
      </div>
    </header>

    <main class="flex-1">
      <RouterView />
    </main>

    <footer class="border-t border-slate-200 dark:border-slate-700 text-sm text-slate-500">
      <div class="max-w-6xl mx-auto px-4 py-4 text-center">YouFeed — aggregatore news</div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { RouterLink, RouterView } from "vue-router";
import ThemeToggle from "@/components/common/ThemeToggle.vue";
</script>
