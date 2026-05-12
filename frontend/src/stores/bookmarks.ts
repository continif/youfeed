import { defineStore } from "pinia";
import { ref } from "vue";
import {
  addBookmark,
  checkBookmarks,
  removeBookmark,
} from "@/services/bookmarks";

/**
 * Cache locale dei bookmark dell'utente loggato (set di article_id).
 * - Si popola in modo lazy: la pagina che mostra una timeline chiama
 *   `hydrate([id1, id2, …])` con gli id correnti; lo store fa una sola call
 *   POST /yf_me/bookmarks/check e popola il set.
 * - `toggle()` aggiorna ottimisticamente lo state e fa la call HTTP.
 */
export const useBookmarksStore = defineStore("bookmarks", () => {
  const ids = ref<Set<number>>(new Set());
  const ready = ref(false);

  function isBookmarked(articleId: number): boolean {
    return ids.value.has(articleId);
  }

  async function hydrate(articleIds: number[]): Promise<void> {
    const missing = articleIds.filter((id) => !ready.value || !ids.value.has(id));
    if (!missing.length) {
      ready.value = true;
      return;
    }
    try {
      const res = await checkBookmarks(missing);
      const next = new Set(ids.value);
      for (const id of res.ids) next.add(id);
      ids.value = next;
      ready.value = true;
    } catch {
      /* non-fatal: l'icona resta "non bookmarked" finché reload */
    }
  }

  async function toggle(articleId: number): Promise<boolean> {
    const wasBookmarked = ids.value.has(articleId);
    const next = new Set(ids.value);
    if (wasBookmarked) next.delete(articleId);
    else next.add(articleId);
    ids.value = next;
    try {
      if (wasBookmarked) await removeBookmark(articleId);
      else await addBookmark(articleId);
      return !wasBookmarked;
    } catch (e) {
      // Rollback ottimistico
      const rollback = new Set(ids.value);
      if (wasBookmarked) rollback.add(articleId);
      else rollback.delete(articleId);
      ids.value = rollback;
      throw e;
    }
  }

  function reset(): void {
    ids.value = new Set();
    ready.value = false;
  }

  return { ids, ready, isBookmarked, hydrate, toggle, reset };
});
