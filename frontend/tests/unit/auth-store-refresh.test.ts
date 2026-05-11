// Test del nuovo metodo `refresh` aggiunto al store auth in Phase 18.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { HTTPError } from "ky";

vi.mock("@/services/auth", () => ({
  getMe: vi.fn(),
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
}));

import * as authApi from "@/services/auth";
import { useAuthStore } from "@/stores/auth";

const mocked = vi.mocked(authApi);

const FAKE_USER = {
  id: 1,
  username: "drtarr",
  email: "drtarr@drtarr.it",
  email_verified: true,
  onboarding_completed_at: null as string | null,
  created_at: "2026-05-06T10:00:00Z",
};

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
});

describe("auth store · refresh", () => {
  it("è no-op se l'utente non è autenticato", async () => {
    const auth = useAuthStore();
    expect(auth.user).toBeNull();
    await auth.refresh();
    expect(mocked.getMe).not.toHaveBeenCalled();
  });

  it("aggiorna lo stato user dopo una mutation backend", async () => {
    mocked.getMe.mockResolvedValueOnce(FAKE_USER);
    const auth = useAuthStore();
    await auth.hydrate();
    expect(auth.user?.onboarding_completed_at).toBeNull();

    // simula PATCH lato backend → next getMe ritorna il nuovo stato
    mocked.getMe.mockResolvedValueOnce({
      ...FAKE_USER,
      onboarding_completed_at: "2026-05-07T10:00:00Z",
    });
    await auth.refresh();
    expect(auth.user?.onboarding_completed_at).toBe("2026-05-07T10:00:00Z");
  });

  it("preserva lo state precedente se getMe fallisce", async () => {
    mocked.getMe.mockResolvedValueOnce(FAKE_USER);
    const auth = useAuthStore();
    await auth.hydrate();

    const httpErr = new HTTPError(
      new Response("", { status: 500 }),
      new Request("http://x/yf_me"),
      {} as never,
    );
    mocked.getMe.mockRejectedValueOnce(httpErr);

    await auth.refresh();
    expect(auth.user).not.toBeNull();
    expect(auth.user?.username).toBe("drtarr");
  });
});
