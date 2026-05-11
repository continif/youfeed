<template>
  <div>
    <header class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-semibold">Categorie</h1>
      <button
        type="button"
        class="px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium"
        @click="openCreate(null)"
      >
        + Nuova categoria
      </button>
    </header>

    <p v-if="loading" class="text-slate-500">Caricamento…</p>
    <p v-if="error" class="text-red-600 dark:text-red-400">{{ error }}</p>

    <p v-if="!loading && !error && tree && tree.tree.length === 0" class="text-slate-500">
      Nessuna categoria. Crea la prima per iniziare a organizzare le fonti.
    </p>

    <CategoryTree
      v-if="tree && tree.tree.length"
      :tree="tree"
      @edit="openEdit"
      @delete="onDelete"
      @reorder="onReorder"
    />

    <!-- Modale CRUD -->
    <div
      v-if="modalOpen"
      class="fixed inset-0 z-40 bg-black/40 flex items-center justify-center p-4"
      @click.self="closeModal"
    >
      <div
        class="bg-white dark:bg-slate-800 rounded-lg shadow-lg max-w-md w-full p-6 space-y-4"
      >
        <h2 class="text-lg font-semibold">
          {{ editingId ? "Modifica categoria" : "Nuova categoria" }}
        </h2>

        <div>
          <label class="block text-sm font-medium mb-1">Nome</label>
          <input
            v-model="formName"
            type="text"
            maxlength="120"
            class="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2"
          />
        </div>

        <div v-if="!editingId">
          <label class="block text-sm font-medium mb-1">
            Sottocategoria di
          </label>
          <select
            v-model="formParentId"
            class="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2"
          >
            <option :value="null">— Nessuna (categoria principale) —</option>
            <option v-for="r in rootCategories" :key="r.id" :value="r.id">{{ r.name }}</option>
          </select>
        </div>

        <div>
          <p class="block text-sm font-medium mb-2">Colore</p>
          <CategoryColorPicker v-model="formColor" />
        </div>

        <div class="flex items-center gap-2">
          <input id="is_public" v-model="formIsPublic" type="checkbox" />
          <label for="is_public" class="text-sm">Categoria pubblica (visibile sul tuo profilo)</label>
        </div>

        <p v-if="formError" class="text-sm text-red-600 dark:text-red-400">{{ formError }}</p>

        <div class="flex gap-2 pt-2">
          <button
            type="button"
            class="flex-1 rounded-md border border-slate-300 dark:border-slate-700 py-2"
            :disabled="saving"
            @click="closeModal"
          >
            Annulla
          </button>
          <button
            type="button"
            class="flex-1 rounded-md bg-blue-600 hover:bg-blue-700 text-white py-2 disabled:opacity-50"
            :disabled="saving || !formName.trim()"
            @click="onSave"
          >
            {{ saving ? "Salvataggio…" : "Salva" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  fetchCategoryTree,
  createCategory,
  updateCategory,
  deleteCategory,
} from "@/services/categories";
import { extractError } from "@/services/api";
import { useToastsStore } from "@/stores/toasts";
import CategoryTree from "@/components/categories/CategoryTree.vue";
import CategoryColorPicker from "@/components/categories/CategoryColorPicker.vue";
import type { CategoryNode, CategoryTreeOut } from "@/types/api";

const toasts = useToastsStore();

const tree = ref<CategoryTreeOut | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

const modalOpen = ref(false);
const editingId = ref<number | null>(null);
const formName = ref("");
const formParentId = ref<number | null>(null);
const formColor = ref<string | null>(null);
const formIsPublic = ref(true);
const saving = ref(false);
const formError = ref<string | null>(null);

const rootCategories = computed(() => tree.value?.tree ?? []);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    tree.value = await fetchCategoryTree();
  } catch (err) {
    const apiErr = await extractError(err);
    error.value = apiErr?.message ?? "Errore nel caricamento.";
  } finally {
    loading.value = false;
  }
}

function openCreate(parentId: number | null) {
  editingId.value = null;
  formName.value = "";
  formParentId.value = parentId;
  formColor.value = null;
  formIsPublic.value = true;
  formError.value = null;
  modalOpen.value = true;
}

function openEdit(node: CategoryNode) {
  editingId.value = node.id;
  formName.value = node.name;
  formParentId.value = node.parent_id;
  formColor.value = node.color;
  formIsPublic.value = node.is_public;
  formError.value = null;
  modalOpen.value = true;
}

function closeModal() {
  modalOpen.value = false;
}

async function onSave() {
  saving.value = true;
  formError.value = null;
  try {
    if (editingId.value === null) {
      await createCategory(formName.value.trim(), formParentId.value, formColor.value);
      toasts.success("Categoria creata.");
    } else {
      await updateCategory(editingId.value, {
        name: formName.value.trim(),
        color: formColor.value,
        is_public: formIsPublic.value,
      });
      toasts.success("Categoria aggiornata.");
    }
    modalOpen.value = false;
    await load();
  } catch (err) {
    const apiErr = await extractError(err);
    formError.value = apiErr?.message ?? "Errore nel salvataggio.";
  } finally {
    saving.value = false;
  }
}

async function onDelete(node: CategoryNode) {
  if (
    !confirm(
      `Eliminare "${node.name}"? Le fonti collegate dovranno essere riassegnate.`,
    )
  )
    return;
  try {
    await deleteCategory(node.id);
    toasts.success("Categoria eliminata.");
    await load();
  } catch (err) {
    const apiErr = await extractError(err);
    toasts.error(apiErr?.message ?? "Impossibile eliminare la categoria.");
  }
}

async function onReorder(_parentId: number | null, orderedIds: number[]) {
  // Persisti la nuova posizione: emettiamo PATCH con `position` per ogni id.
  // L'API accetta la position 0-based.
  try {
    await Promise.all(
      orderedIds.map((id, idx) => updateCategory(id, { position: idx })),
    );
    toasts.success("Ordine salvato.");
  } catch (err) {
    const apiErr = await extractError(err);
    toasts.error(apiErr?.message ?? "Errore nel riordino.");
    await load(); // re-allinea
  }
}

onMounted(load);
</script>
