<template>
  <div class="max-w-xl">
    <h1 class="text-2xl font-semibold mb-6">Aspetto</h1>

    <section class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-6 mb-6">
      <h2 class="font-semibold mb-2">Colore di sfondo</h2>
      <p class="text-sm text-slate-600 dark:text-slate-400 mb-4">
        Sovrascrive il colore di sfondo del tema chiaro/scuro. La preferenza è
        salvata solo nel tuo browser (localStorage).
      </p>

      <!-- Preset rapidi: coerenti coi due temi Tailwind -->
      <div class="flex flex-wrap gap-2 mb-3">
        <button
          v-for="p in presets"
          :key="p.hex"
          type="button"
          class="flex items-center gap-2 px-3 py-1.5 text-sm rounded border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700"
          :class="{ 'ring-2 ring-blue-500': color === p.hex }"
          @click="setColor(p.hex)"
        >
          <span
            class="inline-block w-4 h-4 rounded border border-slate-300 dark:border-slate-600"
            :style="{ backgroundColor: p.hex }"
            aria-hidden="true"
          />
          {{ p.label }}
        </button>
      </div>

      <div class="flex items-center gap-3 mb-4">
        <input
          type="color"
          :value="color || '#fafafa'"
          @input="onPick"
          class="h-10 w-16 rounded border border-slate-300 dark:border-slate-600 cursor-pointer bg-transparent"
          aria-label="Scegli colore di sfondo"
        />
        <input
          type="text"
          :value="color || ''"
          placeholder="#fafafa"
          @change="onTypeHex"
          class="flex-1 px-3 py-2 rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm font-mono"
        />
        <button
          type="button"
          class="px-3 py-2 text-sm rounded border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700"
          :disabled="!color"
          @click="reset"
        >
          Reset
        </button>
      </div>

      <p v-if="invalid" class="text-sm text-red-600">
        Inserisci un colore esadecimale valido (es. <code>#1a2b3c</code>).
      </p>
      <p class="text-xs text-slate-500 dark:text-slate-400">
        Stato attuale:
        <strong>{{ color ? color : "default tema" }}</strong>
      </p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useBackgroundColor } from "@/composables/useBackgroundColor";

const { color, setColor, reset } = useBackgroundColor();
const invalid = ref(false);

const HEX_RE = /^#[0-9a-fA-F]{6}$/;

// Preset coerenti con i background di tema Tailwind:
// - #ffffff = bg-white (tema chiaro)
// - #0f172a = bg-slate-900 (tema scuro, default index.html dark)
const presets = [
  { hex: "#ffffff", label: "Sfondo chiaro" },
  { hex: "#0f172a", label: "Sfondo scuro" },
];

function onPick(e: Event) {
  const v = (e.target as HTMLInputElement).value;
  invalid.value = false;
  setColor(v);
}

function onTypeHex(e: Event) {
  const raw = (e.target as HTMLInputElement).value.trim();
  if (!raw) {
    reset();
    invalid.value = false;
    return;
  }
  if (!HEX_RE.test(raw)) {
    invalid.value = true;
    return;
  }
  invalid.value = false;
  setColor(raw);
}
</script>
