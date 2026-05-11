import { defineStore } from "pinia";
import { ref } from "vue";
import { unreadCount } from "@/services/notifications";
import { useAuthStore } from "@/stores/auth";

const POLL_INTERVAL_MS = 60_000;

export const useNotificationsStore = defineStore("notifications", () => {
  const count = ref(0);
  let timer: number | null = null;

  async function refresh(): Promise<void> {
    const auth = useAuthStore();
    if (!auth.isAuthenticated) {
      count.value = 0;
      return;
    }
    try {
      const res = await unreadCount();
      count.value = res.unread;
    } catch {
      // best-effort, non rompiamo l'UI
    }
  }

  function startPolling(): void {
    if (timer != null) return;
    void refresh();
    timer = window.setInterval(refresh, POLL_INTERVAL_MS);
  }

  function stopPolling(): void {
    if (timer != null) {
      window.clearInterval(timer);
      timer = null;
    }
    count.value = 0;
  }

  return { count, refresh, startPolling, stopPolling };
});
