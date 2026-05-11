<template>
  <div class="min-h-screen flex flex-col">
    <header
      class="sticky top-0 z-20 flex items-center justify-between px-4 py-2 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-700"
    >
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="md:hidden w-9 h-9 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-center"
          aria-label="Apri menu categorie"
          :aria-expanded="drawerOpen"
          @click="drawerOpen = true"
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
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
        <RouterLink to="/me/feed" class="font-bold text-lg">YouFeed</RouterLink>
        <span
          v-if="auth.user"
          class="text-sm text-slate-500 hidden sm:inline"
        >
          Ciao, <strong>{{ auth.user.username }}</strong>
        </span>
      </div>
      <div class="flex-1 max-w-md mx-4 hidden sm:block">
        <SearchBar />
      </div>
      <div class="flex items-center gap-2">
        <NotificationsBell />
        <GearMenu />
      </div>
    </header>

    <div class="flex-1 flex">
      <aside
        v-if="categoryTree.length"
        class="hidden md:block md:w-60 md:min-h-[calc(100vh-3.25rem)] border-r border-slate-200 dark:border-slate-700 px-4 py-4 overflow-y-auto"
      >
        <CategoryNav :tree="categoryTree" />
      </aside>

      <main class="flex-1 px-4 py-6 max-w-6xl mx-auto w-full">
        <RouterView />
      </main>
    </div>

    <MobileDrawer
      :open="drawerOpen"
      :tree="categoryTree"
      @update:open="drawerOpen = $event"
    />

    <OnboardingTour :open="tourOpen" @close="tourOpen = false" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch, watchEffect } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import OnboardingTour from "@/components/onboarding/OnboardingTour.vue";
import CategoryNav from "@/components/layouts/CategoryNav.vue";
import GearMenu from "@/components/layouts/GearMenu.vue";
import MobileDrawer from "@/components/layouts/MobileDrawer.vue";
import NotificationsBell from "@/components/layouts/NotificationsBell.vue";
import SearchBar from "@/components/common/SearchBar.vue";
import { fetchCategoryTree } from "@/services/categories";
import { useNotificationsStore } from "@/stores/notifications";
import type { CategoryNode } from "@/types/api";

const auth = useAuthStore();
const route = useRoute();
const notifStore = useNotificationsStore();

const categoryTree = ref<CategoryNode[]>([]);
const drawerOpen = ref(false);

async function loadCategoryTree() {
  if (!auth.isAuthenticated) return;
  try {
    const res = await fetchCategoryTree();
    categoryTree.value = res.tree;
  } catch {
    // sidebar gracefully vuota
  }
}
onMounted(() => {
  loadCategoryTree();
  if (auth.isAuthenticated) notifStore.startPolling();
});
watch(
  () => auth.isAuthenticated,
  (val) => {
    if (val) {
      loadCategoryTree();
      notifStore.startPolling();
    } else {
      categoryTree.value = [];
      notifStore.stopPolling();
    }
  },
);

// Chiudi drawer al cambio rotta (defensive: il CategoryNav già emette 'navigate'
// chiudendo, ma se l'utente naviga dalla URL bar serve comunque)
watch(
  () => route.fullPath,
  () => {
    drawerOpen.value = false;
  },
);

// Onboarding tour: mostra al primo login
const tourOpen = ref(false);
const shouldOpenTour = computed(
  () => auth.isAuthenticated && auth.user?.onboarding_completed_at === null,
);
watchEffect(() => {
  if (shouldOpenTour.value) tourOpen.value = true;
});
</script>
