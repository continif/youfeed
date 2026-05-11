// Helper colore: WCAG AA contrast + complementari + 16 swatch palette.
// Usa colord per parsing/conversione; manteniamo helper pure per testabilità.

import { colord } from "colord";

/** 16 swatch curate (Tailwind 500-tier per consistenza con la UI). */
export const SWATCHES_16 = [
  "#ef4444", // red
  "#f97316", // orange
  "#f59e0b", // amber
  "#eab308", // yellow
  "#84cc16", // lime
  "#22c55e", // green
  "#10b981", // emerald
  "#14b8a6", // teal
  "#06b6d4", // cyan
  "#0ea5e9", // sky
  "#3b82f6", // blue
  "#6366f1", // indigo
  "#8b5cf6", // violet
  "#a855f7", // purple
  "#d946ef", // fuchsia
  "#ec4899", // pink
] as const;

const HEX_RE = /^#([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;

export function isValidHex(value: string): boolean {
  return HEX_RE.test(value.trim());
}

/** Normalizza un hex valido a forma `#rrggbb` (lower, no alpha). Ritorna null se invalido. */
export function normalizeHex(value: string): string | null {
  const v = value.trim().toLowerCase();
  if (!isValidHex(v)) return null;
  return v.length === 9 ? v.slice(0, 7) : v;
}

/**
 * Ratio di contrasto WCAG (1..21) tra due colori.
 * Implementazione manuale: colord.contrast esiste solo con plugin a11y;
 * preferiamo l'algoritmo standard per ridurre bundle.
 */
export function contrastRatio(fg: string, bg: string): number {
  const a = colord(fg).toRgb();
  const b = colord(bg).toRgb();
  const lA = relativeLuminance(a);
  const lB = relativeLuminance(b);
  const [light, dark] = lA > lB ? [lA, lB] : [lB, lA];
  return (light + 0.05) / (dark + 0.05);
}

function relativeLuminance(rgb: { r: number; g: number; b: number }): number {
  const toLin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  const r = toLin(rgb.r);
  const g = toLin(rgb.g);
  const b = toLin(rgb.b);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG AA per testo non-grande: ratio >= 4.5. */
export function isWcagAA(fg: string, bg: string): boolean {
  return contrastRatio(fg, bg) >= 4.5;
}

/**
 * Sceglie il miglior testo (#000 o #fff) per un colore di sfondo,
 * massimizzando il contrasto.
 */
export function bestTextOn(bg: string): "#000000" | "#ffffff" {
  return contrastRatio("#000000", bg) >= contrastRatio("#ffffff", bg)
    ? "#000000"
    : "#ffffff";
}

/**
 * Ritorna i 5 colori sulla ruota: complementare + 2 split-complementari + 2 analoghi.
 * Output: array di hex `#rrggbb`.
 */
export function complementaryWheel(hex: string): string[] {
  const c = colord(hex);
  if (!c.isValid()) return [];
  const hsl = c.toHsl();
  const h = (hsl.h + 360) % 360;
  const variants = [
    (h + 180) % 360, // complementare
    (h + 150) % 360, // split-complementary
    (h + 210) % 360,
    (h + 30) % 360,  // analogo
    (h + 330) % 360,
  ];
  return variants.map((hue) =>
    colord({ h: hue, s: hsl.s, l: hsl.l }).toHex(),
  );
}
