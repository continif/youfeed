// Test del store Pinia auth: hydrate / login / logout / register.
//
// Mocchiamo `@/services/auth` per evitare HTTP reali. Ricreiamo un nuovo
// pinia per ogni test (setActivePinia) per evitare contamination.

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

const mockedAuthApi = vi.mocked(authApi);

const FAKE_USER = {
  id: 1,
  username: "drtarr",
  email: "drtarr@drtarr.it",
  email_verified: true,
  onboarding_completed_at: null,
  created_at: "2026-05-06T10:00:00Z",
};

function makeHttpError(status: number): HTTPError {
  const response = new Response("", { status });
  const request = new Request("http://localhost/yf_me");
  return new HTTPError(response, request, {} as never);
}

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
});

describe("auth store · hydrate", () => {
  it("starts unhydrated and unauthenticated", () => {
    const auth = useAuthStore();
    expect(auth.hydrated).toBe(false);
    expect(auth.user).toBeNull();
    expect(auth.isAuthenticated).toBe(false);
  });

  it("populates user when /yf_me succeeds", async () => {
    mockedAuthApi.getMe.mockResolvedValueOnce(FAKE_USER);

    const auth = useAuthStore();
    await auth.hydrate();

    expect(auth.hydrated).toBe(true);
    expect(auth.user).toEqual(FAKE_USER);
    expect(auth.isAuthenticated).toBe(true);
  });

  it("treats 401 as anonymous (no warn, user stays null)", async () => {
    mockedAuthApi.getMe.mockRejectedValueOnce(makeHttpError(401));

    const auth = useAuthStore();
    await auth.hydrate();

    expect(auth.hydrated).toBe(true);
    expect(auth.user).toBeNull();
    expect(auth.isAuthenticated).toBe(false);
  });

  it("is idempotent (second call does not re-fetch)", async () => {
    mockedAuthApi.getMe.mockResolvedValue(FAKE_USER);

    const auth = useAuthStore();
    await auth.hydrate();
    await auth.hydrate();

    expect(mockedAuthApi.getMe).toHaveBeenCalledTimes(1);
  });
});

describe("auth store · login", () => {
  it("calls login then getMe and stores user", async () => {
    mockedAuthApi.login.mockResolvedValueOnce({ message: "ok" });
    mockedAuthApi.getMe.mockResolvedValueOnce(FAKE_USER);

    const auth = useAuthStore();
    await auth.login("drtarr", "pwd");

    expect(mockedAuthApi.login).toHaveBeenCalledWith("drtarr", "pwd");
    expect(mockedAuthApi.getMe).toHaveBeenCalledTimes(1);
    expect(auth.user).toEqual(FAKE_USER);
    expect(auth.isAuthenticated).toBe(true);
  });

  it("propagates errors from the login API", async () => {
    mockedAuthApi.login.mockRejectedValueOnce(makeHttpError(401));

    const auth = useAuthStore();
    await expect(auth.login("u", "wrong")).rejects.toBeInstanceOf(HTTPError);
    expect(auth.user).toBeNull();
  });
});

describe("auth store · register", () => {
  it("does not auto-login (must verify email)", async () => {
    mockedAuthApi.register.mockResolvedValueOnce({ message: "ok" });

    const auth = useAuthStore();
    await auth.register("user", "u@x.it", "..longpassword..");

    expect(mockedAuthApi.register).toHaveBeenCalledWith(
      "user",
      "u@x.it",
      "..longpassword..",
    );
    expect(mockedAuthApi.getMe).not.toHaveBeenCalled();
    expect(auth.user).toBeNull();
  });
});

describe("auth store · logout", () => {
  it("clears user even if API call fails (rethrows but state is clean)", async () => {
    mockedAuthApi.getMe.mockResolvedValueOnce(FAKE_USER);
    mockedAuthApi.logout.mockRejectedValueOnce(makeHttpError(500));

    const auth = useAuthStore();
    await auth.hydrate();
    expect(auth.user).not.toBeNull();

    // logout() rilancia, ma il finally pulisce comunque lo stato.
    await expect(auth.logout()).rejects.toBeInstanceOf(HTTPError);

    expect(auth.user).toBeNull();
    expect(auth.isAuthenticated).toBe(false);
  });

  it("calls logout API and clears user on success", async () => {
    mockedAuthApi.getMe.mockResolvedValueOnce(FAKE_USER);
    mockedAuthApi.logout.mockResolvedValueOnce({ message: "bye" });

    const auth = useAuthStore();
    await auth.hydrate();
    await auth.logout();

    expect(mockedAuthApi.logout).toHaveBeenCalledTimes(1);
    expect(auth.user).toBeNull();
  });
});
