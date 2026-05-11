// Test del toasts store: push/dismiss/clear + helper success/error/info + auto-TTL.

import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";

import { useToastsStore } from "@/stores/toasts";

beforeEach(() => {
  setActivePinia(createPinia());
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("toasts store", () => {
  it("starts empty", () => {
    const t = useToastsStore();
    expect(t.toasts).toEqual([]);
  });

  it("push assigns incremental ids", () => {
    const t = useToastsStore();
    const id1 = t.push("info", "first");
    const id2 = t.push("error", "second");
    expect(id1).toBe(1);
    expect(id2).toBe(2);
    expect(t.toasts).toHaveLength(2);
    expect(t.toasts[0].message).toBe("first");
    expect(t.toasts[1].type).toBe("error");
  });

  it("dismiss removes the toast by id (no-op for unknown)", () => {
    const t = useToastsStore();
    const id = t.push("info", "to remove");
    t.dismiss(999); // unknown
    expect(t.toasts).toHaveLength(1);
    t.dismiss(id);
    expect(t.toasts).toHaveLength(0);
  });

  it("auto-dismisses after the default TTL", () => {
    const t = useToastsStore();
    t.success("ciao");
    expect(t.toasts).toHaveLength(1);
    vi.advanceTimersByTime(4000);
    expect(t.toasts).toHaveLength(1);
    vi.advanceTimersByTime(1000); // TTL default 4500ms totali
    expect(t.toasts).toHaveLength(0);
  });

  it("respects custom TTL", () => {
    const t = useToastsStore();
    t.error("breve", 1000);
    vi.advanceTimersByTime(900);
    expect(t.toasts).toHaveLength(1);
    vi.advanceTimersByTime(200);
    expect(t.toasts).toHaveLength(0);
  });

  it("ttl <= 0 disables auto-dismiss", () => {
    const t = useToastsStore();
    t.push("info", "persistente", 0);
    vi.advanceTimersByTime(60_000);
    expect(t.toasts).toHaveLength(1);
  });

  it("clear empties all toasts immediately", () => {
    const t = useToastsStore();
    t.push("info", "a");
    t.push("error", "b");
    t.clear();
    expect(t.toasts).toEqual([]);
  });

  it.each([
    ["success", "ok"],
    ["error", "fail"],
    ["info", "neutro"],
  ] as const)("helper %s sets the right type", (type, msg) => {
    const t = useToastsStore();
    t[type](msg);
    expect(t.toasts[0].type).toBe(type);
    expect(t.toasts[0].message).toBe(msg);
  });
});
