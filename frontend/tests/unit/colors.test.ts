// Test degli helper colore: WCAG contrast, hex validation, complementari.

import { describe, it, expect } from "vitest";
import {
  SWATCHES_16,
  isValidHex,
  normalizeHex,
  contrastRatio,
  isWcagAA,
  bestTextOn,
  complementaryWheel,
} from "@/lib/colors";

describe("colors · isValidHex / normalizeHex", () => {
  it("accepts #rrggbb (case-insensitive)", () => {
    expect(isValidHex("#3b82f6")).toBe(true);
    expect(isValidHex("#3B82F6")).toBe(true);
    expect(isValidHex("#ABCDEF")).toBe(true);
  });

  it("accepts #rrggbbaa (with alpha)", () => {
    expect(isValidHex("#3b82f6ff")).toBe(true);
  });

  it("rejects invalid hex", () => {
    expect(isValidHex("#fff")).toBe(false); // short form non supportato
    expect(isValidHex("3b82f6")).toBe(false); // mancante #
    expect(isValidHex("#zzzzzz")).toBe(false);
    expect(isValidHex("")).toBe(false);
    expect(isValidHex("#1234")).toBe(false);
  });

  it("normalizes to lowercase, strips alpha", () => {
    expect(normalizeHex("#3B82F6")).toBe("#3b82f6");
    expect(normalizeHex("#3b82f6ff")).toBe("#3b82f6");
    expect(normalizeHex(" #3B82F6 ")).toBe("#3b82f6");
  });

  it("returns null on invalid", () => {
    expect(normalizeHex("not-hex")).toBeNull();
    expect(normalizeHex("#abc")).toBeNull();
  });
});

describe("colors · contrastRatio", () => {
  it("ratio black on white is 21:1", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 0);
  });

  it("ratio same color is 1:1", () => {
    expect(contrastRatio("#777777", "#777777")).toBeCloseTo(1, 1);
  });

  it("is symmetric", () => {
    expect(contrastRatio("#3b82f6", "#ffffff")).toBeCloseTo(
      contrastRatio("#ffffff", "#3b82f6"),
      5,
    );
  });
});

describe("colors · isWcagAA", () => {
  it("black on white passes", () => {
    expect(isWcagAA("#000000", "#ffffff")).toBe(true);
  });

  it("yellow on white fails AA (low contrast)", () => {
    expect(isWcagAA("#fde047", "#ffffff")).toBe(false);
  });

  it("white on dark blue passes", () => {
    expect(isWcagAA("#ffffff", "#1e40af")).toBe(true);
  });
});

describe("colors · bestTextOn", () => {
  it("returns white on dark colors", () => {
    expect(bestTextOn("#000000")).toBe("#ffffff");
    expect(bestTextOn("#1e40af")).toBe("#ffffff");
  });

  it("returns black on light colors", () => {
    expect(bestTextOn("#ffffff")).toBe("#000000");
    expect(bestTextOn("#fde047")).toBe("#000000");
  });
});

describe("colors · complementaryWheel", () => {
  it("returns 5 hex colors (complementary + 2 split + 2 analogous)", () => {
    const wheel = complementaryWheel("#ff0000");
    expect(wheel).toHaveLength(5);
    for (const hex of wheel) {
      expect(isValidHex(hex)).toBe(true);
    }
  });

  it("includes the 180° complementary first", () => {
    const wheel = complementaryWheel("#ff0000");
    // red → cyan (~#00ffff). Tolleriamo lievi shift di colord.
    const first = wheel[0];
    expect(first.toLowerCase()).toMatch(/^#00ff/);
  });

  it("returns empty array on invalid input", () => {
    expect(complementaryWheel("not-a-color")).toEqual([]);
  });
});

describe("colors · SWATCHES_16", () => {
  it("has exactly 16 valid hex colors", () => {
    expect(SWATCHES_16).toHaveLength(16);
    for (const c of SWATCHES_16) {
      expect(isValidHex(c)).toBe(true);
    }
  });
});
