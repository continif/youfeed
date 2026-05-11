// Store globale per toast/notifiche transitorie.
// L'API è minima: push({type, message}) o le helper success/error/info.
// Il componente <Toaster> consuma `toasts` e gestisce auto-dismiss.

import { defineStore } from "pinia";
import { ref } from "vue";

export type ToastType = "success" | "error" | "info";

export interface Toast {
  id: number;
  type: ToastType;
  message: string;
}

const DEFAULT_TTL_MS = 4500;

export const useToastsStore = defineStore("toasts", () => {
  const toasts = ref<Toast[]>([]);
  let nextId = 1;

  function push(type: ToastType, message: string, ttl: number = DEFAULT_TTL_MS): number {
    const id = nextId++;
    toasts.value.push({ id, type, message });
    if (ttl > 0) {
      setTimeout(() => dismiss(id), ttl);
    }
    return id;
  }

  function dismiss(id: number): void {
    const i = toasts.value.findIndex((t) => t.id === id);
    if (i >= 0) toasts.value.splice(i, 1);
  }

  function clear(): void {
    toasts.value = [];
  }

  return {
    toasts,
    push,
    dismiss,
    clear,
    success: (msg: string, ttl?: number) => push("success", msg, ttl),
    error: (msg: string, ttl?: number) => push("error", msg, ttl),
    info: (msg: string, ttl?: number) => push("info", msg, ttl),
  };
});
