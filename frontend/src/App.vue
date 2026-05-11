<template>
  <div>
    <RouterView />
    <Toaster />
  </div>
</template>

<script setup lang="ts">
import { RouterView } from "vue-router";
import Toaster from "@/components/common/Toaster.vue";
// Inizializza il composable: legge `localStorage.yf_bg_color` e applica
// il colore di sfondo al body subito al boot (no FOUC).
import { useBackgroundColor } from "@/composables/useBackgroundColor";
useBackgroundColor();
</script>
