// Wrapper ky con CSRF auto: legge il cookie `yf_csrf` (NON HttpOnly) e
// lo replica in header `X-YF-CSRF` per le mutating requests.
//
// Nota: yf_session è HttpOnly, quindi non lo vediamo da JS — il browser
// lo invia automaticamente perché siamo same-origin (Apache fa il proxy
// /yf_* -> backend, e Vite proxy in dev fa lo stesso).

import ky, { HTTPError } from "ky";
import type { ApiError } from "@/types/api";

function readCookie(name: string): string | undefined {
  const match = document.cookie.match(
    new RegExp("(?:^|; )" + name.replace(/[.$?*|{}()[\]\\/+^]/g, "\\$&") + "=([^;]*)"),
  );
  return match ? decodeURIComponent(match[1]) : undefined;
}

const MUTATING = new Set(["POST", "PATCH", "PUT", "DELETE"]);

// ky vuole un prefixUrl assoluto: in browser usiamo window.location.origin
// (Vite/Apache fanno proxy /yf_* allo stesso origin).
const PREFIX_URL =
  typeof window !== "undefined" && window.location?.origin
    ? window.location.origin + "/"
    : "http://localhost/";

export const api = ky.create({
  prefixUrl: PREFIX_URL,
  timeout: 15_000,
  retry: { limit: 0 },
  hooks: {
    beforeRequest: [
      (request) => {
        if (MUTATING.has(request.method)) {
          const token = readCookie("yf_csrf");
          if (token) request.headers.set("X-YF-CSRF", token);
        }
      },
    ],
  },
});

/**
 * Estrae il payload `{error: {code, message}}` standard del backend.
 * Ritorna `null` se il body non è parseabile o non ha lo shape atteso.
 */
export async function extractError(err: unknown): Promise<ApiError["error"] | null> {
  if (!(err instanceof HTTPError)) return null;
  try {
    const body = await err.response.json();
    if (
      body &&
      typeof body === "object" &&
      "error" in body &&
      typeof body.error === "object"
    ) {
      return body.error as ApiError["error"];
    }
  } catch {
    /* ignore */
  }
  return null;
}
