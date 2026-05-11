// Test del composable useTrackingConsent: state machine, persistenza
// localStorage, lazy-load gated del fingerprint.

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { nextTick } from "vue";

import { useTrackingConsent, _internals } from "@/composables/useTrackingConsent";

beforeEach(() => {
  localStorage.clear();
  _internals.resetForTests();
  vi.clearAllMocks();
  vi.resetModules();
});

afterEach(() => {
  localStorage.clear();
  _internals.resetForTests();
});

describe("useTrackingConsent · state machine", () => {
  it("starts as 'unknown' if nothing in localStorage", () => {
    const { consent } = useTrackingConsent();
    expect(consent.value).toBe("unknown");
  });

  it("grant() sets 'granted' and persists to localStorage", async () => {
    const { consent, grant } = useTrackingConsent();
    grant();
    await nextTick();
    expect(consent.value).toBe("granted");
    expect(localStorage.getItem(_internals.KEY)).toBe("granted");
  });

  it("deny() sets 'denied' and persists", async () => {
    const { consent, deny } = useTrackingConsent();
    deny();
    await nextTick();
    expect(consent.value).toBe("denied");
    expect(localStorage.getItem(_internals.KEY)).toBe("denied");
  });

  it("reset() clears localStorage", async () => {
    const { grant, reset } = useTrackingConsent();
    grant();
    await nextTick();
    expect(localStorage.getItem(_internals.KEY)).toBe("granted");
    reset();
    await nextTick();
    expect(localStorage.getItem(_internals.KEY)).toBeNull();
  });

  it("two consumers share the same singleton state", () => {
    const a = useTrackingConsent();
    a.grant();
    const b = useTrackingConsent();
    expect(b.consent.value).toBe("granted");
  });
});

describe("useTrackingConsent · getFingerprint gating", () => {
  it("returns null when consent !== 'granted'", async () => {
    const { getFingerprint } = useTrackingConsent();
    expect(await getFingerprint()).toBeNull();
  });

  it("returns null after consent is denied (was unknown)", async () => {
    const { deny, getFingerprint } = useTrackingConsent();
    deny();
    expect(await getFingerprint()).toBeNull();
  });

  it("returns a visitorId when granted (lazy import is mocked)", async () => {
    vi.doMock("@fingerprintjs/fingerprintjs", () => ({
      load: vi.fn().mockResolvedValue({
        get: vi.fn().mockResolvedValue({ visitorId: "abc-123" }),
      }),
    }));
    // Re-import per applicare il mock dinamico
    const { useTrackingConsent: useFresh, _internals: fresh } = await import(
      "@/composables/useTrackingConsent"
    );
    fresh.resetForTests();
    const { grant, getFingerprint } = useFresh();
    grant();
    const fp = await getFingerprint();
    expect(fp).toBe("abc-123");
  });

  it("memoizes the fingerprint across calls", async () => {
    const loadSpy = vi.fn().mockResolvedValue({
      get: vi.fn().mockResolvedValue({ visitorId: "memoized" }),
    });
    vi.doMock("@fingerprintjs/fingerprintjs", () => ({ load: loadSpy }));
    const { useTrackingConsent: useFresh, _internals: fresh } = await import(
      "@/composables/useTrackingConsent"
    );
    fresh.resetForTests();
    const { grant, getFingerprint } = useFresh();
    grant();
    await getFingerprint();
    await getFingerprint();
    expect(loadSpy).toHaveBeenCalledTimes(1);
  });
});
