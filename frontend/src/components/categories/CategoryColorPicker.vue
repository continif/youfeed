<template>
  <div class="space-y-3">
    <!-- 16 swatch palette -->
    <div>
      <p class="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Palette</p>
      <div class="grid grid-cols-8 gap-1">
        <button
          v-for="swatch in SWATCHES_16"
          :key="swatch"
          type="button"
          class="w-7 h-7 rounded border border-slate-300 dark:border-slate-700 transition hover:scale-110"
          :style="{ background: swatch }"
          :class="{ 'ring-2 ring-offset-2 ring-blue-500': selected === swatch }"
          :aria-label="swatch"
          @click="select(swatch)"
        />
      </div>
    </div>

    <!-- Custom hex input -->
    <div>
      <label class="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
        Colore custom (#rrggbb)
      </label>
      <div class="flex items-center gap-2">
        <input
          v-model="customInput"
          type="text"
          placeholder="#3b82f6"
          maxlength="9"
          class="flex-1 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 py-1 text-sm font-mono"
          :class="{ 'border-red-500': customInput && !isCustomValid }"
          @blur="commitCustom"
          @keydown.enter.prevent="commitCustom"
        />
        <span
          class="w-7 h-7 rounded border border-slate-300 dark:border-slate-700"
          :style="{ background: isCustomValid ? customInput : 'transparent' }"
        />
      </div>
      <p v-if="customInput && !isCustomValid" class="mt-1 text-xs text-red-600 dark:text-red-400">
        Hex non valido (atteso `#rrggbb`).
      </p>
    </div>

    <!-- Complementari (suggerimenti) -->
    <div v-if="wheel.length">
      <p class="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
        Suggerimenti dalla ruota
      </p>
      <div class="flex gap-1">
        <button
          v-for="hex in wheel"
          :key="hex"
          type="button"
          class="w-7 h-7 rounded border border-slate-300 dark:border-slate-700 hover:scale-110 transition"
          :style="{ background: hex }"
          :aria-label="hex"
          @click="select(hex)"
        />
      </div>
    </div>

    <!-- Preview + WCAG -->
    <div
      v-if="selected"
      class="rounded-md border px-3 py-2 flex items-center justify-between text-sm"
      :style="{ background: selected, color: textColor, borderColor: selected }"
    >
      <span class="font-medium">Anteprima testo</span>
      <span class="font-mono text-xs">
        {{ contrastLight.toFixed(1) }}:1 / {{ contrastDark.toFixed(1) }}:1
      </span>
    </div>
    <p v-if="selected && !wcagOk" class="text-xs text-amber-700 dark:text-amber-400">
      Attenzione: contrasto sotto WCAG AA (4.5:1) sia con bianco che con nero.
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  SWATCHES_16,
  isValidHex,
  normalizeHex,
  bestTextOn,
  contrastRatio,
  complementaryWheel,
} from "@/lib/colors";

const props = defineProps<{ modelValue: string | null }>();
const emit = defineEmits<{ (e: "update:modelValue", v: string | null): void }>();

const selected = computed(() => props.modelValue);
const customInput = ref(props.modelValue ?? "");

watch(
  () => props.modelValue,
  (v) => {
    customInput.value = v ?? "";
  },
);

const isCustomValid = computed(() => isValidHex(customInput.value));

function select(hex: string) {
  const norm = normalizeHex(hex);
  if (norm) emit("update:modelValue", norm);
}

function commitCustom() {
  const norm = normalizeHex(customInput.value);
  if (norm) {
    emit("update:modelValue", norm);
    customInput.value = norm;
  } else if (customInput.value === "") {
    emit("update:modelValue", null);
  }
}

const wheel = computed(() => (selected.value ? complementaryWheel(selected.value) : []));

const textColor = computed(() => (selected.value ? bestTextOn(selected.value) : "#000000"));

const contrastLight = computed(() =>
  selected.value ? contrastRatio("#ffffff", selected.value) : 1,
);
const contrastDark = computed(() =>
  selected.value ? contrastRatio("#000000", selected.value) : 1,
);

const wcagOk = computed(() =>
  Math.max(contrastLight.value, contrastDark.value) >= 4.5,
);
</script>
