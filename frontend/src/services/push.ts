/**
 * Web Push helpers (Phase 1.2.E).
 *
 * Pipeline tipica:
 *   1. ensureSWRegistered() — registra /sw.js
 *   2. getVapidKey() — fetch chiave pubblica dal backend
 *   3. subscribeUser() — chiede permesso → PushManager.subscribe() → POST al backend
 *   4. unsubscribeUser() — annulla locale + DELETE backend
 *
 * Tutte le funzioni sono resistenti a browser senza supporto: ritornano
 * un esito esplicito invece di throware in modo opaco.
 */

import { api } from "@/services/api";
import type {
  MessageOut,
  PushSubscriptionOut,
  VapidKeyOut,
} from "@/types/api";

const SW_PATH = "/sw.js";

export function pushSupported(): boolean {
  return (
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

export async function ensureSWRegistered(): Promise<ServiceWorkerRegistration | null> {
  if (!pushSupported()) return null;
  let reg = await navigator.serviceWorker.getRegistration(SW_PATH);
  if (!reg) {
    reg = await navigator.serviceWorker.register(SW_PATH);
  }
  await navigator.serviceWorker.ready;
  return reg;
}

export async function getVapidKey(): Promise<VapidKeyOut> {
  return api.get("yf_push/vapid-key").json<VapidKeyOut>();
}

function urlBase64ToUint8Array(b64: string): Uint8Array {
  const padding = "=".repeat((4 - (b64.length % 4)) % 4);
  const base64 = (b64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

function subscriptionToJson(sub: PushSubscription): {
  endpoint: string;
  keys: { p256dh: string; auth: string };
} {
  const json = sub.toJSON() as {
    endpoint?: string;
    keys?: { p256dh?: string; auth?: string };
  };
  return {
    endpoint: json.endpoint ?? "",
    keys: {
      p256dh: json.keys?.p256dh ?? "",
      auth: json.keys?.auth ?? "",
    },
  };
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null;
  const reg = await navigator.serviceWorker.getRegistration(SW_PATH);
  if (!reg) return null;
  return reg.pushManager.getSubscription();
}

export type SubscribeResult =
  | { status: "subscribed"; subscription: PushSubscription }
  | { status: "permission_denied" }
  | { status: "unsupported" }
  | { status: "not_configured" }
  | { status: "error"; message: string };

export async function subscribeUser(): Promise<SubscribeResult> {
  if (!pushSupported()) return { status: "unsupported" };

  const vapid = await getVapidKey();
  if (!vapid.configured || !vapid.public_key) {
    return { status: "not_configured" };
  }

  const permission = await Notification.requestPermission();
  if (permission !== "granted") return { status: "permission_denied" };

  const reg = await ensureSWRegistered();
  if (!reg) return { status: "unsupported" };

  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    // Le tipizzazioni TS recenti ($ArrayBufferLike vs $ArrayBuffer) impongono
    // BufferSource → passiamo direttamente il .buffer dell'Uint8Array.
    const key = urlBase64ToUint8Array(vapid.public_key);
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: key.buffer.slice(0) as ArrayBuffer,
    });
  }

  try {
    await api
      .post("yf_me/push/subscriptions", { json: subscriptionToJson(sub) })
      .json<PushSubscriptionOut>();
  } catch (e) {
    return { status: "error", message: String((e as Error).message ?? e) };
  }
  return { status: "subscribed", subscription: sub };
}

export async function unsubscribeUser(): Promise<boolean> {
  const sub = await currentSubscription();
  if (!sub) return true;
  // Cancella prima sul browser, poi sul backend (per endpoint)
  await sub.unsubscribe();

  try {
    // Il backend ha le sub indicizzate per endpoint; recupero quella attuale
    const subs = await api
      .get("yf_me/push/subscriptions")
      .json<PushSubscriptionOut[]>();
    const match = subs.find((s) => s.endpoint === sub.endpoint);
    if (match) {
      await api.delete(`yf_me/push/subscriptions/${match.id}`);
    }
  } catch {
    // Best-effort lato server
  }
  return true;
}

export async function sendTestPush(): Promise<MessageOut> {
  return api.post("yf_me/push/test").json<MessageOut>();
}

export async function listSubscriptions(): Promise<PushSubscriptionOut[]> {
  return api.get("yf_me/push/subscriptions").json<PushSubscriptionOut[]>();
}
