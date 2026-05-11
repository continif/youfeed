<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition-opacity duration-200"
      leave-active-class="transition-opacity duration-200"
      enter-from-class="opacity-0"
      leave-to-class="opacity-0"
    >
      <div
        v-if="open"
        class="md:hidden fixed inset-0 bg-black/50 z-40"
        aria-hidden="true"
        @click="$emit('update:open', false)"
      />
    </Transition>

    <Transition
      enter-active-class="transition-transform duration-200 ease-out"
      leave-active-class="transition-transform duration-200 ease-in"
      enter-from-class="-translate-x-full"
      leave-to-class="-translate-x-full"
    >
      <aside
        v-if="open"
        ref="drawerEl"
        class="md:hidden fixed left-0 top-0 bottom-0 w-72 max-w-[85vw] bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-700 z-50 overflow-y-auto px-4 py-4"
        role="dialog"
        aria-modal="true"
        aria-label="Categorie"
      >
        <div class="flex items-center justify-between mb-4">
          <span class="font-bold text-lg">YouFeed</span>
          <button
            type="button"
            class="w-9 h-9 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-center"
            aria-label="Chiudi menu"
            @click="$emit('update:open', false)"
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
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <CategoryNav :tree="tree" @navigate="$emit('update:open', false)" />
      </aside>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import CategoryNav from "@/components/layouts/CategoryNav.vue";
import type { CategoryNode } from "@/types/api";

const props = defineProps<{ open: boolean; tree: CategoryNode[] }>();
const emit = defineEmits<{ "update:open": [value: boolean] }>();

const drawerEl = ref<HTMLElement | null>(null);

watch(
  () => props.open,
  (val) => {
    document.body.style.overflow = val ? "hidden" : "";
  },
);

function onEscape(e: KeyboardEvent) {
  if (e.key === "Escape" && props.open) emit("update:open", false);
}

onMounted(() => document.addEventListener("keydown", onEscape));
onBeforeUnmount(() => {
  document.removeEventListener("keydown", onEscape);
  document.body.style.overflow = "";
});
</script>
