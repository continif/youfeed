<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
    @click.self="onSkip"
  >
    <div class="bg-white dark:bg-slate-800 rounded-lg shadow-xl max-w-lg w-full p-6 space-y-4">
      <!-- Progress -->
      <div class="flex items-center gap-1.5">
        <div
          v-for="(_, idx) in ONBOARDING_STEPS"
          :key="idx"
          :class="[
            'h-1 flex-1 rounded',
            idx < stepIndex
              ? 'bg-blue-500'
              : idx === stepIndex
                ? 'bg-blue-400'
                : 'bg-slate-200 dark:bg-slate-700',
          ]"
        />
      </div>

      <header>
        <h2 class="text-xl font-semibold">{{ currentStep.title }}</h2>
        <p class="text-sm text-slate-600 dark:text-slate-400 mt-2">{{ currentStep.body }}</p>
      </header>

      <!-- Step-specific body -->
      <div class="min-h-[140px]">
        <!-- Categories (multi-select) -->
        <div v-if="currentStep.key === 'categories'" class="space-y-2 max-h-72 overflow-auto">
          <label
            v-for="cat in SUGGESTED_CATEGORIES"
            :key="cat.slug"
            class="flex items-start gap-3 p-2 rounded border border-slate-200 dark:border-slate-700 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-700/40"
          >
            <input
              v-model="selectedCategorySlugs"
              type="checkbox"
              :value="cat.slug"
              class="mt-1"
            />
            <span
              class="w-4 h-4 rounded mt-1"
              :style="{ background: cat.defaultColor }"
            />
            <span class="flex-1 min-w-0">
              <span class="font-medium block">{{ cat.name }}</span>
              <span class="text-xs text-slate-500">{{ cat.description }}</span>
            </span>
          </label>
        </div>

        <!-- Sources -->
        <div v-else-if="currentStep.key === 'sources'" class="text-sm text-slate-600 dark:text-slate-400">
          <p>
            Le fonti popolari sono visibili dalla sezione
            <strong>Fonti → Aggiungi fonte</strong>: scegli quelle italiane per categoria
            (Politica, Sport, ecc.).
          </p>
          <RouterLink
            to="/me/sources/add"
            class="inline-block mt-3 text-blue-600 hover:underline"
            @click="onSkip"
            >Apri "Aggiungi fonte" →</RouterLink
          >
        </div>

        <!-- Color picker demo -->
        <div v-else-if="currentStep.key === 'color-picker'" class="space-y-2">
          <p class="text-sm text-slate-600 dark:text-slate-400">
            Ogni categoria può avere un colore: prova qui.
          </p>
          <CategoryColorPicker v-model="demoColor" />
        </div>

        <!-- Privacy -->
        <div v-else-if="currentStep.key === 'privacy'" class="space-y-3">
          <p class="text-sm text-slate-600 dark:text-slate-400">
            Stato attuale:
            <strong>
              {{
                consent === "granted"
                  ? "Consenso accordato"
                  : consent === "denied"
                    ? "Tracciamento disattivato"
                    : "Da decidere"
              }}
            </strong>
          </p>
          <div class="flex gap-2">
            <button
              type="button"
              class="rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm px-3 py-2"
              :disabled="consent === 'granted'"
              @click="grant"
            >
              Accetta
            </button>
            <button
              type="button"
              class="rounded-md border border-slate-300 dark:border-slate-700 text-sm px-3 py-2"
              :disabled="consent === 'denied'"
              @click="deny"
            >
              Rifiuta
            </button>
          </div>
        </div>

        <!-- Public feed preview -->
        <div v-else-if="currentStep.key === 'public-feed'" class="text-sm text-slate-600 dark:text-slate-400">
          <p>
            Le categorie pubbliche compongono il tuo profilo all'URL:
          </p>
          <code class="mt-2 block px-3 py-2 bg-slate-100 dark:bg-slate-900 rounded text-blue-700 dark:text-blue-300">
            youfeed.it/{{ auth.user?.username || "tuo-username" }}
          </code>
          <p class="mt-2">
            Da quella stessa pagina è disponibile l'export RSS automatico
            (<code>/yf_users/{{ auth.user?.username || "username" }}/feed.rss</code>).
          </p>
        </div>

        <p v-if="categoriesError" class="text-sm text-red-600 dark:text-red-400">
          {{ categoriesError }}
        </p>
      </div>

      <!-- Footer actions -->
      <footer class="flex items-center justify-between pt-3 border-t border-slate-200 dark:border-slate-700">
        <button
          type="button"
          class="text-sm text-slate-500 hover:underline"
          @click="onSkip"
        >
          Salta tour
        </button>
        <div class="flex gap-2">
          <button
            v-if="stepIndex > 0"
            type="button"
            class="rounded-md border border-slate-300 dark:border-slate-700 text-sm px-3 py-2"
            @click="prev"
          >
            ← Indietro
          </button>
          <button
            type="button"
            class="rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2 disabled:opacity-50"
            :disabled="busy"
            @click="next"
          >
            {{ nextLabel }}
          </button>
        </div>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import CategoryColorPicker from "@/components/categories/CategoryColorPicker.vue";
import {
  ONBOARDING_STEPS,
  SUGGESTED_CATEGORIES,
} from "@/lib/onboarding-data";
import { createCategory } from "@/services/categories";
import { completeOnboarding } from "@/services/me";
import { useAuthStore } from "@/stores/auth";
import { useToastsStore } from "@/stores/toasts";
import { useTrackingConsent } from "@/composables/useTrackingConsent";
import { extractError } from "@/services/api";

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ (e: "close"): void }>();

const auth = useAuthStore();
const toasts = useToastsStore();
const { consent, grant, deny } = useTrackingConsent();

const stepIndex = ref(0);
const currentStep = computed(() => ONBOARDING_STEPS[stepIndex.value]);

const selectedCategorySlugs = ref<string[]>([]);
const demoColor = ref<string | null>("#3b82f6");
const busy = ref(false);
const categoriesError = ref<string | null>(null);

const isLast = computed(() => stepIndex.value === ONBOARDING_STEPS.length - 1);

const nextLabel = computed(() => {
  if (busy.value) return "Attendi…";
  if (currentStep.value.primaryActionLabel) return currentStep.value.primaryActionLabel;
  return isLast.value ? "Inizia" : "Avanti";
});

async function next() {
  busy.value = true;
  categoriesError.value = null;
  try {
    if (currentStep.value.key === "categories" && selectedCategorySlugs.value.length) {
      const selected = SUGGESTED_CATEGORIES.filter((c) =>
        selectedCategorySlugs.value.includes(c.slug),
      );
      // Crea le categorie scelte in sequenza (poche unità, no batch endpoint)
      for (const cat of selected) {
        await createCategory(cat.name, null, cat.defaultColor);
      }
      toasts.success(`Create ${selected.length} categorie.`);
    }

    if (isLast.value) {
      await onComplete();
      return;
    }
    stepIndex.value += 1;
  } catch (err) {
    const apiErr = await extractError(err);
    categoriesError.value = apiErr?.message ?? "Errore durante questo passaggio.";
  } finally {
    busy.value = false;
  }
}

function prev() {
  if (stepIndex.value > 0) stepIndex.value -= 1;
}

async function onComplete() {
  try {
    await completeOnboarding();
    await auth.refresh();
    toasts.success("Tour completato. Buon feed!");
  } catch {
    /* niente toast errore: l'utente può sempre rifare il tour */
  } finally {
    emit("close");
  }
}

function onSkip() {
  emit("close");
}

// `props` viene usato dal parent per controllare la visibilità.
void props;
</script>
