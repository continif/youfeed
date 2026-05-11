<template>
  <div>
    <!-- Root level -->
    <VueDraggable
      v-model="roots"
      :animation="180"
      handle=".drag-handle"
      class="space-y-2"
      @end="onReorder(null, roots)"
    >
      <div
        v-for="root in roots"
        :key="root.id"
        class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg"
      >
        <div
          class="flex items-center gap-2 p-3"
          :style="root.color ? { borderLeft: `4px solid ${root.color}` } : {}"
        >
          <span class="drag-handle cursor-move text-slate-400 select-none">⋮⋮</span>
          <strong class="flex-1 truncate">{{ root.name }}</strong>
          <span
            v-if="root.is_public"
            class="text-[0.7rem] px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300"
            >pubblica</span
          >
          <button
            type="button"
            class="text-xs text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
            @click="emit('edit', root)"
          >
            Modifica
          </button>
          <button
            type="button"
            class="text-xs text-red-600 hover:underline"
            @click="emit('delete', root)"
          >
            Elimina
          </button>
        </div>

        <!-- Children level (single nesting in MVP) -->
        <VueDraggable
          v-if="root.children?.length"
          v-model="root.children"
          :animation="180"
          handle=".drag-handle"
          class="space-y-1 px-4 pb-3"
          @end="onReorder(root.id, root.children)"
        >
          <div
            v-for="child in root.children"
            :key="child.id"
            class="flex items-center gap-2 p-2 rounded border border-slate-100 dark:border-slate-700/50"
            :style="child.color ? { borderLeft: `3px solid ${child.color}` } : {}"
          >
            <span class="drag-handle cursor-move text-slate-400 select-none">⋮⋮</span>
            <span class="flex-1 truncate text-sm">{{ child.name }}</span>
            <button
              type="button"
              class="text-xs text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
              @click="emit('edit', child)"
            >
              Modifica
            </button>
            <button
              type="button"
              class="text-xs text-red-600 hover:underline"
              @click="emit('delete', child)"
            >
              Elimina
            </button>
          </div>
        </VueDraggable>
      </div>
    </VueDraggable>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { VueDraggable } from "vue-draggable-plus";
import type { CategoryNode, CategoryTreeOut } from "@/types/api";

const props = defineProps<{ tree: CategoryTreeOut }>();
const emit = defineEmits<{
  (e: "edit", node: CategoryNode): void;
  (e: "delete", node: CategoryNode): void;
  (e: "reorder", parentId: number | null, orderedIds: number[]): void;
}>();

const roots = ref<CategoryNode[]>([]);

watch(
  () => props.tree,
  (t) => {
    roots.value = JSON.parse(JSON.stringify(t.tree)) as CategoryNode[];
  },
  { immediate: true, deep: true },
);

function onReorder(parentId: number | null, list: CategoryNode[]) {
  emit("reorder", parentId, list.map((n) => n.id));
}
</script>
