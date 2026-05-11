// Test del wrapper API: CSRF auto-injection + extractError.
//
// Mocchiamo `globalThis.fetch` per intercettare le richieste senza fare HTTP
// vere. ky usa fetch internamente, quindi catchiamo lì le call.

import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { HTTPError } from "ky";

import { api, extractError } from "@/services/api";

function setCookie(value: string): void {
  // jsdom: document.cookie è scrivibile (set per chiave)
  document.cookie = value;
}

function clearCookies(): void {
  for (const c of document.cookie.split(";")) {
    const name = c.split("=")[0]?.trim();
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:01 GMT; path=/`;
  }
}

describe("services/api", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    clearCookies();
    fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    clearCookies();
    vi.restoreAllMocks();
  });

  it("does not inject X-YF-CSRF on GET requests", async () => {
    setCookie("yf_csrf=token-123");

    await api.get("yf_health").json();

    const call = fetchMock.mock.calls[0];
    const request = call[0] as Request;
    expect(request.method).toBe("GET");
    expect(request.headers.get("X-YF-CSRF")).toBeNull();
  });

  it("injects X-YF-CSRF on POST requests when cookie is present", async () => {
    setCookie("yf_csrf=secret-token-xyz");

    await api.post("yf_auth/login", { json: { identifier: "u", password: "p" } }).json();

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.method).toBe("POST");
    expect(request.headers.get("X-YF-CSRF")).toBe("secret-token-xyz");
  });

  it("does not inject X-YF-CSRF on POST when cookie is missing", async () => {
    // Niente cookie

    await api.post("yf_auth/login", { json: {} }).json();

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.headers.get("X-YF-CSRF")).toBeNull();
  });

  it.each([
    ["PATCH", () => api.patch("x").json().catch(() => {})],
    ["DELETE", () => api.delete("x").json().catch(() => {})],
    ["PUT", () => api.put("x").json().catch(() => {})],
  ])("injects X-YF-CSRF on %s", async (_label, run) => {
    setCookie("yf_csrf=mt");
    await run();
    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.headers.get("X-YF-CSRF")).toBe("mt");
  });

  it("decodes URL-encoded cookie values", async () => {
    setCookie("yf_csrf=" + encodeURIComponent("a/b+c=d"));

    await api.post("yf_track").json().catch(() => {});

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.headers.get("X-YF-CSRF")).toBe("a/b+c=d");
  });
});

describe("extractError", () => {
  it("returns the {code, message} payload for backend AppError", async () => {
    const body = JSON.stringify({ error: { code: "csrf_failed", message: "no token" } });
    const response = new Response(body, {
      status: 403,
      headers: { "content-type": "application/json" },
    });
    const fakeReq = new Request("http://x/y");
    const httpErr = new HTTPError(response, fakeReq, {} as never);

    const out = await extractError(httpErr);
    expect(out).toEqual({ code: "csrf_failed", message: "no token" });
  });

  it("returns null for non-HTTPError", async () => {
    expect(await extractError(new Error("boom"))).toBeNull();
    expect(await extractError("string error")).toBeNull();
  });

  it("returns null when body is not JSON", async () => {
    const response = new Response("not json", { status: 500 });
    const fakeReq = new Request("http://x/y");
    const httpErr = new HTTPError(response, fakeReq, {} as never);
    expect(await extractError(httpErr)).toBeNull();
  });

  it("returns null when JSON has no `error` key", async () => {
    const response = new Response(JSON.stringify({ msg: "x" }), {
      status: 500,
      headers: { "content-type": "application/json" },
    });
    const fakeReq = new Request("http://x/y");
    const httpErr = new HTTPError(response, fakeReq, {} as never);
    expect(await extractError(httpErr)).toBeNull();
  });
});
