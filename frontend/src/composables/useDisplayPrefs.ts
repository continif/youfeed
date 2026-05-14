/**
 * Preferenze di visualizzazione device-local (localStorage).
 *
 * Per ora una sola voce: `showImages` (mostra/nascondi immagini nelle
 * card del feed). Default ON. Usata da `ArticleCard.vue` per scegliere
 * il layout con o senza foto.
 *
 * Pattern singleton modulare come `useBackgroundColor`: stato condiviso
 * fra tutte le istanze. Salva su localStorage in modo reattivo.
 */

import { ref, watchEffect } from "vue";


const KEY_SHOW_IMAGES = "yf_display_show_images";

function _readShowImages(): boolean {
  try {
    const raw = localStorage.getItem(KEY_SHOW_IMAGES);
    if (raw === "0" || raw === "false") return false;
  } catch {
    /* localStorage bloccato */
  }
  return true; // default: immagini ON
}

const _showImages = ref<boolean>(_readShowImages());

watchEffect(() => {
  try {
    localStorage.setItem(KEY_SHOW_IMAGES, _showImages.value ? "1" : "0");
  } catch {
    /* ignore */
  }
});


export function useDisplayPrefs() {
  function setShowImages(v: boolean): void {
    _showImages.value = v;
  }
  function toggleShowImages(): void {
    _showImages.value = !_showImages.value;
  }
  return {
    showImages: _showImages,
    setShowImages,
    toggleShowImages,
  };
}
