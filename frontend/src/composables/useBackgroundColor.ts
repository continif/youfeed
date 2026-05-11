/**
 * Background color personalizzabile dall'utente, persistito in
 * `localStorage.yf_bg_color`. Sovrascrive il colore di sfondo del tema
 * (dark/light) finché non viene resettato.
 *
 * Pattern singleton modulare: `state` reactive condiviso tra tutte le
 * istanze dell'app (anche tra componenti diversi che chiamano useBackgroundColor).
 */
import { ref, watchEffect } from "vue";

const STORAGE_KEY = "yf_bg_color";
const HEX_RE = /^#[0-9a-fA-F]{6}$/;

function _read(): string | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw && HEX_RE.test(raw)) return raw;
  } catch {
    /* localStorage può essere bloccato — ignoriamo */
  }
  return null;
}

const _color = ref<string | null>(_read());

// Applica il colore al body. `null` rimuove l'override (torna al tema).
function _apply(color: string | null) {
  if (typeof document === "undefined") return;
  if (color) {
    document.body.style.backgroundColor = color;
  } else {
    document.body.style.removeProperty("background-color");
  }
}

// Auto-apply: ogni volta che cambia _color, aggiorna body + localStorage.
watchEffect(() => {
  _apply(_color.value);
  try {
    if (_color.value) {
      localStorage.setItem(STORAGE_KEY, _color.value);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    /* localStorage bloccato — soft fail */
  }
});

export function useBackgroundColor() {
  function setColor(color: string | null) {
    if (color === null) {
      _color.value = null;
      return;
    }
    if (!HEX_RE.test(color)) {
      throw new Error(`invalid hex color: ${color}`);
    }
    _color.value = color.toLowerCase();
  }

  function reset() {
    _color.value = null;
  }

  return {
    color: _color,
    setColor,
    reset,
  };
}

// Esposto per i test: re-leggere da localStorage manualmente
export const _internals = {
  reread: () => {
    _color.value = _read();
  },
};
