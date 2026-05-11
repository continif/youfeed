// Test sui dati statici dell'onboarding: shape categorie, step, colors validi.

import { describe, it, expect } from "vitest";
import {
  ONBOARDING_STEPS,
  SUGGESTED_CATEGORIES,
} from "@/lib/onboarding-data";
import { isValidHex } from "@/lib/colors";

describe("SUGGESTED_CATEGORIES", () => {
  it("ha esattamente 10 categorie suggerite", () => {
    expect(SUGGESTED_CATEGORIES).toHaveLength(10);
  });

  it("ogni categoria ha slug + name + description + defaultColor", () => {
    for (const cat of SUGGESTED_CATEGORIES) {
      expect(cat.slug).toMatch(/^[a-z][a-z0-9_-]*$/);
      expect(cat.name.length).toBeGreaterThan(0);
      expect(cat.description.length).toBeGreaterThan(0);
      expect(isValidHex(cat.defaultColor)).toBe(true);
    }
  });

  it("gli slug sono unici", () => {
    const slugs = SUGGESTED_CATEGORIES.map((c) => c.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
  });

  it("include le categorie italiane chiave", () => {
    const slugs = SUGGESTED_CATEGORIES.map((c) => c.slug);
    expect(slugs).toContain("politica");
    expect(slugs).toContain("cronaca");
    expect(slugs).toContain("sport");
    expect(slugs).toContain("tecnologia");
  });
});

describe("ONBOARDING_STEPS", () => {
  it("ha 7 step come da spec", () => {
    expect(ONBOARDING_STEPS).toHaveLength(7);
  });

  it("ogni step ha key + title + body", () => {
    for (const s of ONBOARDING_STEPS) {
      expect(s.key.length).toBeGreaterThan(0);
      expect(s.title.length).toBeGreaterThan(0);
      expect(s.body.length).toBeGreaterThan(0);
    }
  });

  it("le key sono uniche e nell'ordine atteso", () => {
    const keys = ONBOARDING_STEPS.map((s) => s.key);
    expect(keys).toEqual([
      "welcome",
      "categories",
      "sources",
      "color-picker",
      "privacy",
      "public-feed",
      "done",
    ]);
  });

  it("lo step 'categories' e 'done' hanno una primaryActionLabel", () => {
    const cat = ONBOARDING_STEPS.find((s) => s.key === "categories");
    const done = ONBOARDING_STEPS.find((s) => s.key === "done");
    expect(cat?.primaryActionLabel).toBeTruthy();
    expect(done?.primaryActionLabel).toBeTruthy();
  });
});
