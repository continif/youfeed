<template>
  <article
    class="break-inside-avoid mb-4 bg-white dark:bg-slate-800 rounded-lg overflow-hidden shadow-sm transition-shadow duration-150 hover:shadow-2xl hover:shadow-black/40 dark:hover:shadow-white/30"
    :class="{
      'border-2': true,
      'border-slate-200 dark:border-slate-700': !item.category_color,
    }"
    :style="cardStyle"
    :data-article-id="item.id"
  >
    <div v-if="hasImage" class="relative">
      <RouterLink :to="`/me/article/${item.id}`" class="block">
        <picture>
          <source
            v-if="item.image_local_url"
            media="(max-width: 599px)"
            :srcset="item.image_local_url.replace('_d.webp', '_m.webp')"
          />
          <img
            :src="item.image_local_url || item.image_url || ''"
            :alt="item.title"
            :width="item.image_width ?? undefined"
            :height="item.image_height ?? undefined"
            loading="lazy"
            class="w-full h-auto block"
            @error="onImgError"
          />
        </picture>
      </RouterLink>
      <!-- Bookmark toggle: overlay angolo alto-destra, sempre floppy 💾 -->
      <button
        type="button"
        class="absolute right-2 top-2 w-8 h-8 flex items-center justify-center rounded-md text-base leading-none transition-colors"
        :class="
          isBookmarked
            ? 'bg-blue-600 hover:bg-blue-700 text-white ring-1 ring-white/60'
            : 'bg-black/70 hover:bg-black/85 text-white'
        "
        :title="isBookmarked ? 'Rimuovi dai salvati' : 'Salva'"
        :aria-label="isBookmarked ? 'Rimuovi dai salvati' : 'Salva'"
        :aria-pressed="isBookmarked"
        @click.prevent.stop="onToggleBookmark"
      >💾</button>
      <!-- Ora pubblicazione: sotto immagine, allineata a destra -->
      <time
        :datetime="item.published_at"
        :title="item.published_at"
        class="absolute right-2 bottom-1 text-[0.72rem] text-white px-1.5 py-0.5 rounded bg-black/55"
      >
        {{ relTime }}
      </time>
    </div>

    <div class="p-3">
      <h2 class="font-semibold text-base leading-snug mb-1 flex items-start gap-2">
        <RouterLink
          :to="`/me/article/${item.id}`"
          class="flex-1 hover:text-blue-600 dark:hover:text-blue-400"
          >{{ item.title }}</RouterLink
        >
        <button
          v-if="!hasImage"
          type="button"
          class="w-7 h-7 flex items-center justify-center rounded-md text-sm leading-none shrink-0 transition-colors"
          :class="
            isBookmarked
              ? 'bg-blue-600 hover:bg-blue-700 text-white'
              : 'bg-black/80 hover:bg-black text-white'
          "
          :title="isBookmarked ? 'Rimuovi dai salvati' : 'Salva'"
          :aria-label="isBookmarked ? 'Rimuovi dai salvati' : 'Salva'"
          :aria-pressed="isBookmarked"
          @click.prevent.stop="onToggleBookmark"
        >💾</button>
      </h2>
      <p
        v-if="cleanDescription"
        class="text-sm text-slate-600 dark:text-slate-400 mb-2"
      >
        {{ cleanDescription }}
      </p>
      <div class="flex items-center justify-between text-xs text-slate-500">
        <span class="font-medium">{{ item.source.title || item.source.url_site }}</span>
        <!-- Senza immagine la time va inline a destra qui -->
        <time
          v-if="!hasImage"
          :datetime="item.published_at"
          :title="item.published_at"
          >{{ relTime }}</time
        >
      </div>
      <ul v-if="item.topics.length" class="flex flex-wrap gap-1 mt-2">
        <li
          v-for="t in displayedTopics"
          :key="t.id"
        >
          <RouterLink
            :to="topicLinkTo(t.id)"
            :class="[
              'text-[0.7rem] px-2 py-0.5 rounded-full border inline-block hover:opacity-80 transition-opacity',
              topicColor(t.type),
            ]"
          >
            {{ t.display_name }}
          </RouterLink>
        </li>
        <li
          v-if="item.topics.length > MAX_TOPICS"
          class="text-[0.7rem] px-2 py-0.5 rounded-full border inline-block text-slate-500 dark:text-slate-400 border-slate-300 dark:border-slate-600"
          :title="`${item.topics.length - MAX_TOPICS} altri topic`"
        >
          +{{ item.topics.length - MAX_TOPICS }}
        </li>
      </ul>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { formatDistanceToNow, parseISO } from "date-fns";
import { it } from "date-fns/locale";
import { useAuthStore } from "@/stores/auth";
import { useBookmarksStore } from "@/stores/bookmarks";
import { useToastsStore } from "@/stores/toasts";
import type { ArticleListItem } from "@/types/api";

const props = defineProps<{ item: ArticleListItem }>();
const route = useRoute();
const auth = useAuthStore();
const bookmarksStore = useBookmarksStore();
const toasts = useToastsStore();

const isBookmarked = computed(() => bookmarksStore.isBookmarked(props.item.id));

async function onToggleBookmark() {
  if (!auth.isAuthenticated) {
    toasts.error("Accedi per salvare gli articoli.");
    return;
  }
  try {
    await bookmarksStore.toggle(props.item.id);
  } catch {
    toasts.error("Impossibile aggiornare il bookmark.");
  }
}

const MAX_TOPICS = 12;
const displayedTopics = computed(() => props.item.topics.slice(0, MAX_TOPICS));

function topicLinkTo(topicId: number) {
  const cat = route.params.categoryId;
  const path = typeof cat === "string" && cat ? `/me/feed/${cat}` : "/me/feed";
  return { path, query: { topic: topicId } };
}

const cardStyle = computed(() =>
  props.item.category_color
    ? { borderColor: props.item.category_color, borderWidth: "2px" }
    : {},
);

const imageFailed = ref(false);
const hasImage = computed(
  () => !imageFailed.value && !!(props.item.image_local_url || props.item.image_url),
);

function onImgError() {
  imageFailed.value = true;
}

const cleanDescription = computed(() => {
  const raw = props.item.description ?? "";
  if (!raw) return "";
  // strip HTML tags + collapse whitespace + truncate
  const tmp = document.createElement("div");
  tmp.innerHTML = raw;
  const text = (tmp.textContent || "").replace(/\s+/g, " ").trim();
  return text.length > 180 ? text.slice(0, 179).trimEnd() + "…" : text;
});

const relTime = computed(() => {
  try {
    return formatDistanceToNow(parseISO(props.item.published_at), {
      locale: it,
      addSuffix: true,
    });
  } catch {
    return props.item.published_at;
  }
});

function topicColor(type: string): string {
  if (type === "brand") {
    return "border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/20";
  }
  if (type === "person") {
    return "border-blue-200 dark:border-blue-900 text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/20";
  }
  if (type === "subject") {
    return "border-emerald-200 dark:border-emerald-900 text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-900/20";
  }
  return "border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-700/40";
}
</script>
