import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { HTTPError } from "ky";
import * as authApi from "@/services/auth";
import type { UserOut } from "@/types/api";

export const useAuthStore = defineStore("auth", () => {
  const user = ref<UserOut | null>(null);
  const hydrated = ref(false);

  const isAuthenticated = computed(() => user.value !== null);

  /**
   * Tenta di idratare lo stato chiedendo `/yf_me`. 401 = anonimo (atteso).
   */
  async function hydrate(): Promise<void> {
    if (hydrated.value) return;
    try {
      user.value = await authApi.getMe();
    } catch (err) {
      if (!(err instanceof HTTPError) || err.response.status !== 401) {
        // eslint-disable-next-line no-console
        console.warn("[auth] hydrate failed", err);
      }
      user.value = null;
    } finally {
      hydrated.value = true;
    }
  }

  async function login(identifier: string, password: string): Promise<void> {
    await authApi.login(identifier, password);
    user.value = await authApi.getMe();
  }

  async function register(username: string, email: string, password: string): Promise<void> {
    await authApi.register(username, email, password);
    // Non logghiamo automaticamente: l'utente deve verificare l'email.
  }

  async function logout(): Promise<void> {
    try {
      await authApi.logout();
    } finally {
      user.value = null;
    }
  }

  /** Re-fetcha `/yf_me` per allineare lo stato dopo una mutation
   *  (es. `PATCH /yf_me` per `onboarding_completed_at`). No-op se anonimo. */
  async function refresh(): Promise<void> {
    if (!user.value) return;
    try {
      user.value = await authApi.getMe();
    } catch {
      /* lasciamo lo stato precedente */
    }
  }

  return { user, hydrated, isAuthenticated, hydrate, login, register, logout, refresh };
});
