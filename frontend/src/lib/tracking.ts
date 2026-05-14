// Helper centralizzato per emettere eventi a `POST /yf_track` (vedi
// .claude/PERSONALIZED.md → Phase 1.A).
//
// Caratteristiche:
// - Gated sul consenso tracking (`useTrackingConsent` → 'granted').
// - Aggiunge l'header `X-YF-Fingerprint` se il fp è già stato calcolato.
// - Usa `fetch(..., { keepalive: true })` così il browser garantisce la
//   consegna anche su navigation/unload (utile per `original_open` che
//   apre una nuova tab e per `dwell_*` sparati su `visibilitychange`).
// - Dedup automatico per `impression`: una sola hit per (article_id,
//   tab session) → evita di gonfiare il count con Vue ri-render.
//
// API: `trackEvent("preview_open", { type: "article", id: 42 })`.

import { useTrackingConsent } from "@/composables/useTrackingConsent";

export type TrackEventType =
  | "impression"
  | "preview_open"
  | "dwell_5s"
  | "dwell_15s"
  | "dwell_60s"
  | "original_open"
  | "related_click"
  | "bookmark"
  | "share"
  | "search";

export interface TrackTarget {
  type: "article" | "topic" | "source";
  id: number | string;
}

const seenImpressions = new Set<string>();

function readCookie(name: string): string | undefined {
  const match = document.cookie.match(
    new RegExp("(?:^|; )" + name.replace(/[.$?*|{}()[\]\\/+^]/g, "\\$&") + "=([^;]*)"),
  );
  return match ? decodeURIComponent(match[1]) : undefined;
}

export async function trackEvent(
  eventType: TrackEventType,
  target?: TrackTarget,
  metadata?: Record<string, unknown>,
): Promise<void> {
  const { consent, getFingerprint } = useTrackingConsent();
  if (consent.value !== "granted") return;

  // Dedup impression: una sola per (article_id, tab session).
  if (eventType === "impression" && target) {
    const key = `${target.type}:${target.id}`;
    if (seenImpressions.has(key)) return;
    seenImpressions.add(key);
  }

  // Fingerprint è async ma già cached dopo prima chiamata → noop nella maggior
  // parte dei casi. Se l'utente ha appena dato consenso, la prima call carica
  // FingerprintJS (1×) e poi è cache.
  const fp = await getFingerprint().catch(() => null);

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (fp) headers["X-YF-Fingerprint"] = fp;
  const csrf = readCookie("yf_csrf");
  if (csrf) headers["X-YF-CSRF"] = csrf;

  const body = {
    event_type: eventType,
    target_type: target?.type ?? null,
    target_id: target ? String(target.id) : null,
    metadata: metadata ?? null,
  };

  try {
    await fetch("/yf_track", {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      // keepalive: anche su unload/navigation il browser tenta la consegna.
      // Dimensione massima 64KB, qui sotto i 256B sempre. ✓
      keepalive: true,
      credentials: "same-origin",
    });
  } catch {
    // Silente: tracking è best-effort, non deve mai rompere la UX.
  }
}

// Esposto solo per i test
export const _internals = {
  resetImpressionDedup: () => seenImpressions.clear(),
};
