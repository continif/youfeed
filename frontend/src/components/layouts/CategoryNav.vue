<template>
  <nav aria-label="Categorie">
    <p class="px-3 text-xs uppercase tracking-wide text-slate-500 mb-1">
      Le mie categorie
    </p>
    <ul>
      <li>
        <RouterLink
          to="/me/feed"
          class="flex items-center gap-2 px-3 py-1.5 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 text-sm"
          :class="{
            'bg-slate-100 dark:bg-slate-800 font-medium': activeCategoryId === null,
          }"
          @click="$emit('navigate')"
        >
          <span class="inline-block w-2.5 h-2.5 rounded-full bg-slate-400" />
          <span class="truncate">Tutte</span>
        </RouterLink>
      </li>
      <li v-for="root in tree" :key="root.id">
        <RouterLink
          :to="`/me/feed/${root.id}`"
          class="flex items-center gap-2 px-3 py-1.5 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 text-sm"
          :class="{
            'bg-slate-100 dark:bg-slate-800 font-medium':
              activeCategoryId === root.id,
          }"
          @click="$emit('navigate')"
        >
          <span
            class="inline-block w-2.5 h-2.5 rounded-full"
            :style="{ backgroundColor: root.color || '#94a3b8' }"
          />
          <span class="truncate">{{ root.name }}</span>
        </RouterLink>
        <ul v-if="root.children?.length" class="ml-4">
          <li v-for="child in root.children" :key="child.id">
            <RouterLink
              :to="`/me/feed/${child.id}`"
              class="flex items-center gap-2 px-3 py-1 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 text-xs"
              :class="{
                'bg-slate-100 dark:bg-slate-800 font-medium':
                  activeCategoryId === child.id,
              }"
              @click="$emit('navigate')"
            >
              <span
                class="inline-block w-2 h-2 rounded-full"
                :style="{ backgroundColor: child.color || '#94a3b8' }"
              />
              <span class="truncate">{{ child.name }}</span>
            </RouterLink>
          </li>
        </ul>
      </li>
    </ul>
  </nav>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { RouterLink, useRoute } from "vue-router";
import type { CategoryNode } from "@/types/api";

defineProps<{ tree: CategoryNode[] }>();
defineEmits<{ navigate: [] }>();

const route = useRoute();
const activeCategoryId = computed<number | null>(() => {
  const v = route.params.categoryId;
  if (typeof v === "string" && v) {
    const n = parseInt(v, 10);
    return Number.isFinite(n) ? n : null;
  }
  return null;
});
</script>
