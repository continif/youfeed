<template>
  <div>
    <header class="mb-6">
      <h1 class="text-2xl font-semibold">Aggiungi una fonte</h1>
      <p class="text-sm text-slate-500">
        Inserisci l'URL di un sito o scegli da quelli popolari.
      </p>
    </header>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <SourceWizard ref="wizardRef" @added="onAdded" />

      <FeaturedSourcesGallery @select="onPickFeatured" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import SourceWizard from "@/components/sources/SourceWizard.vue";
import FeaturedSourcesGallery from "@/components/sources/FeaturedSourcesGallery.vue";
import { useToastsStore } from "@/stores/toasts";
import type { FeaturedSourceItem } from "@/types/api";

const router = useRouter();
const toasts = useToastsStore();

interface WizardExposed {
  presetFromFeatured: (item: FeaturedSourceItem) => void;
}
const wizardRef = ref<InstanceType<typeof SourceWizard> & WizardExposed>();

function onPickFeatured(item: FeaturedSourceItem) {
  wizardRef.value?.presetFromFeatured(item);
}

async function onAdded(_userSourceId: number) {
  toasts.success("Fonte aggiunta al tuo feed.");
  await router.push({ name: "sources" });
}
</script>
