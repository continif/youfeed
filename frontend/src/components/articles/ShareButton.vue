<template>
  <div class="relative inline-block" @click.stop>
    <button
      type="button"
      class="w-8 h-8 flex items-center justify-center rounded-md text-base leading-none transition-colors bg-black/70 hover:bg-blue-600 text-white"
      :title="open ? 'Chiudi' : 'Condividi'"
      :aria-label="open ? 'Chiudi menu condivisione' : 'Condividi articolo'"
      :aria-expanded="open"
      aria-haspopup="true"
      @click.prevent="toggleMenu"
    >
      <!-- icona "share" -->
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        class="w-4 h-4"
        aria-hidden="true"
      >
        <circle cx="18" cy="5" r="3" />
        <circle cx="6" cy="12" r="3" />
        <circle cx="18" cy="19" r="3" />
        <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
        <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
      </svg>
    </button>

    <div
      v-if="open"
      ref="menuEl"
      class="absolute z-30 min-w-[180px] rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-lg py-1 text-sm"
      :class="
        props.popoverDirection === 'down'
          ? 'right-0 top-full mt-2'
          : 'left-0 bottom-full mb-2'
      "
      role="menu"
    >
      <a
        v-for="t in targets"
        :key="t.id"
        :href="t.href"
        target="_blank"
        rel="noopener noreferrer"
        role="menuitem"
        class="flex items-center gap-2 px-3 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-800"
        @click="onTarget(t.id)"
      >
        <span aria-hidden="true">{{ t.icon }}</span>
        <span>{{ t.label }}</span>
      </a>

      <button
        type="button"
        role="menuitem"
        class="w-full text-left flex items-center gap-2 px-3 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-800"
        @click="onCopy"
      >
        <span aria-hidden="true">🔗</span>
        <span>Copia link</span>
      </button>

      <button
        v-if="hasNativeShare"
        type="button"
        role="menuitem"
        class="w-full text-left flex items-center gap-2 px-3 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 border-t border-slate-200 dark:border-slate-700"
        @click="onNativeShare"
      >
        <span aria-hidden="true">📲</span>
        <span>Condividi…</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { trackEvent } from "@/lib/tracking";
import { useToastsStore } from "@/stores/toasts";

const props = withDefaults(
  defineProps<{
    articleId: number;
    title: string;
    url: string;
    /** Direzione di apertura del popover. 'down' (default) per buttons in
     *  alto, 'up' per buttons in basso. */
    popoverDirection?: "up" | "down";
  }>(),
  { popoverDirection: "down" },
);

const toasts = useToastsStore();
const open = ref(false);
const menuEl = ref<HTMLElement | null>(null);

const hasNativeShare = computed(
  () => typeof navigator !== "undefined" && typeof navigator.share === "function",
);

// Target social: ognuno ha un id (per il tracking), un'icona, un label e
// l'URL intent ufficiale. Substack non ha un share-intent pubblico → la
// gestiamo via clipboard sotto "Copia link" (qui non compare).
const targets = computed(() => {
  const u = encodeURIComponent(props.url);
  const t = encodeURIComponent(props.title);
  const tu = encodeURIComponent(`${props.title} — ${props.url}`);
  return [
    {
      id: "linkedin",
      label: "LinkedIn",
      icon: "in",
      href: `https://www.linkedin.com/sharing/share-offsite/?url=${u}`,
    },
    {
      id: "whatsapp",
      label: "WhatsApp",
      icon: "💬",
      href: `https://wa.me/?text=${tu}`,
    },
    {
      id: "threads",
      label: "Threads",
      icon: "@",
      href: `https://threads.net/intent/post?text=${tu}`,
    },
    {
      id: "x",
      label: "X",
      icon: "𝕏",
      href: `https://twitter.com/intent/tweet?text=${t}&url=${u}`,
    },
  ];
});

function toggleMenu() {
  open.value = !open.value;
  if (open.value) {
    // Listener globale per chiusura su click esterno / Escape
    setTimeout(() => {
      window.addEventListener("click", onOutsideClick);
      window.addEventListener("keydown", onEscape);
    }, 0);
  } else {
    cleanupListeners();
  }
}

function onOutsideClick(e: MouseEvent) {
  if (!menuEl.value) return;
  if (!(e.target instanceof Node)) return;
  if (!menuEl.value.contains(e.target)) close();
}

function onEscape(e: KeyboardEvent) {
  if (e.key === "Escape") close();
}

function close() {
  open.value = false;
  cleanupListeners();
}

function cleanupListeners() {
  window.removeEventListener("click", onOutsideClick);
  window.removeEventListener("keydown", onEscape);
}

onBeforeUnmount(cleanupListeners);

function onTarget(id: string) {
  trackEvent(
    "share",
    { type: "article", id: props.articleId },
    { to: id },
  );
  close();
}

async function onCopy() {
  try {
    await navigator.clipboard.writeText(props.url);
    toasts.success("Link copiato negli appunti");
  } catch {
    toasts.error("Impossibile copiare il link");
  }
  trackEvent(
    "share",
    { type: "article", id: props.articleId },
    { to: "copy" },
  );
  close();
}

async function onNativeShare() {
  try {
    await navigator.share({
      title: props.title,
      url: props.url,
    });
    trackEvent(
      "share",
      { type: "article", id: props.articleId },
      { to: "native" },
    );
  } catch {
    // AbortError quando l'utente annulla — non logghiamo nulla
  }
  close();
}
</script>
