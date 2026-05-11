// Composable centrale per il consenso al tracking (impression/click via /yf_track
// + fingerprint anti-fraud). Lo stato persiste in localStorage.
//
// Stati:
//   - "unknown" : utente non ha ancora deciso (default → cookie banner)
//   - "granted" : ha dato consenso esplicito
//   - "denied"  : ha rifiutato (FingerprintJS NON viene caricato)

import { ref, watchEffect } from "vue";

const KEY = "yf_tracking_consent";
type ConsentValue = "unknown" | "granted" | "denied";

const consent = ref<ConsentValue>(loadInitial());
let fpPromise: Promise<string | null> | null = null;

function loadInitial(): ConsentValue {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw === "granted" || raw === "denied") return raw;
  } catch {
    /* localStorage bloccato */
  }
  return "unknown";
}

watchEffect(() => {
  try {
    if (consent.value === "unknown") {
      localStorage.removeItem(KEY);
    } else {
      localStorage.setItem(KEY, consent.value);
    }
  } catch {
    /* ignore */
  }
});

export function useTrackingConsent() {
  function grant() {
    consent.value = "granted";
  }
  function deny() {
    consent.value = "denied";
    // Invalida il fingerprint precedente (se l'utente prima aveva accettato)
    fpPromise = null;
  }
  function reset() {
    consent.value = "unknown";
    fpPromise = null;
  }

  /**
   * Calcola (o ritorna in cache) il fingerprint visitorId. Lazy: importa
   * FingerprintJS solo se l'utente ha dato consenso, così il bundle resta
   * fuori dalla pagina di chi rifiuta.
   * Ritorna null se consent != granted.
   */
  async function getFingerprint(): Promise<string | null> {
    if (consent.value !== "granted") return null;
    if (!fpPromise) {
      fpPromise = (async () => {
        try {
          const FpJS = await import("@fingerprintjs/fingerprintjs");
          const agent = await FpJS.load();
          const result = await agent.get();
          return result.visitorId;
        } catch (err) {
          // eslint-disable-next-line no-console
          console.warn("[fingerprint] failed", err);
          return null;
        }
      })();
    }
    return fpPromise;
  }

  return {
    consent,
    grant,
    deny,
    reset,
    getFingerprint,
  };
}

// Uso testabile interno
export const _internals = {
  KEY,
  resetForTests: () => {
    consent.value = "unknown";
    fpPromise = null;
  },
};
