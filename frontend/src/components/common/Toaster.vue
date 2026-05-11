<template>
  <Teleport to="body">
    <div
      class="fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-[calc(100%-2rem)] pointer-events-none"
      role="status"
      aria-live="polite"
    >
      <TransitionGroup name="toast" tag="div" class="flex flex-col gap-2">
        <div
          v-for="t in toasts.toasts"
          :key="t.id"
          :class="[
            'pointer-events-auto rounded-md shadow-md border px-4 py-3 text-sm flex items-start gap-3',
            t.type === 'success' &&
              'bg-emerald-50 dark:bg-emerald-900/40 border-emerald-200 dark:border-emerald-800 text-emerald-900 dark:text-emerald-100',
            t.type === 'error' &&
              'bg-red-50 dark:bg-red-900/40 border-red-200 dark:border-red-800 text-red-900 dark:text-red-100',
            t.type === 'info' &&
              'bg-slate-50 dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100',
          ]"
        >
          <span class="flex-1">{{ t.message }}</span>
          <button
            type="button"
            class="text-slate-500 hover:text-slate-700 dark:hover:text-slate-200"
            :aria-label="'Chiudi'"
            @click="toasts.dismiss(t.id)"
          >
            ×
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { useToastsStore } from "@/stores/toasts";

const toasts = useToastsStore();
</script>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.18s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
</style>
