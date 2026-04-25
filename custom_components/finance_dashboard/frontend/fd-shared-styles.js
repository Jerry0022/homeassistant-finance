/**
 * Shared styles, formatters, and utilities for Finance Dashboard components.
 *
 * All dashboard components read from window._fd to ensure visual
 * consistency and avoid duplicating CSS / helper functions.
 * The export keywords also remain for future ES-module migration.
 */

/** EUR currency formatter (German locale). */
export function eur(v) {
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
  }).format(v || 0);
}

/** Percentage formatter. */
export function pct(v) {
  return `${Math.round(v || 0)}%`;
}

/** Escape HTML to prevent XSS from user-provided names. */
export function esc(s) {
  if (!s) return "";
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

/**
 * Escape HTML without DOM round-trip (hot-path safe).
 * Replaces &, <, >, ", ' with named entities.
 */
export function escHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Category color mapping. */
export const CAT_COLORS = {
  housing: "#3b82f6",
  loans: "#e74c3c",
  food: "#f97316",
  utilities: "#eab308",
  insurance: "#8b5cf6",
  subscriptions: "#ec4899",
  transport: "#06b6d4",
  cleaning: "#a855f7",
  income: "#4ecca3",
  transfers: "#6b7280",
  other: "#6b7280",
};

/** Category label mapping (German). */
export const CAT_LABELS = {
  housing: "Wohnen",
  loans: "Kredite",
  food: "Lebensmittel",
  utilities: "Nebenkosten",
  insurance: "Versicherung",
  subscriptions: "Abos",
  transport: "Mobilität",
  cleaning: "Reinigung",
  income: "Einkommen",
  transfers: "Überträge",
  other: "Sonstiges",
};

/** Member color palette for household charts. */
export const MEMBER_COLORS = [
  "#3b82f6", "#8b5cf6", "#f97316", "#ec4899", "#06b6d4",
];

/** German month names (abbreviated). */
export const MONTH_NAMES = [
  "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
  "Jul", "Aug", "Sep", "Okt", "Nov", "Dez",
];

/**
 * CSS custom properties and base styles shared across all dashboard components.
 * Components include this via: `<style>${window._fd.SHARED_CSS}${LOCAL_CSS}</style>` in their shadow root.
 */
export const SHARED_CSS = `
:host {
  --bg: var(--primary-background-color, #0a0a0f);
  --sf: var(--card-background-color, #12121a);
  --sf2: #1a1a28;
  --bd: rgba(255,255,255,0.06);
  --tx: var(--primary-text-color, #e0e0e0);
  --tx2: var(--secondary-text-color, #9898a8);
  --ac: var(--accent-color, #4ecca3);
  --dg: #e74c3c;
  --wn: #f39c12;
  --bl: #3b82f6;
  --pp: #8b5cf6;
  --r: 14px;
  display: block;
  font-family: 'Segoe UI', system-ui, sans-serif;
  color: var(--tx);
}
.pos { color: var(--ac); }
.neg { color: var(--dg); }
.neu { color: var(--tx2); }
.card {
  background: var(--sf);
  border: 1px solid var(--bd);
  border-radius: var(--r);
}
.card-h {
  padding: 14px 18px;
  border-bottom: 1px solid var(--bd);
  font-size: 14px;
  font-weight: 600;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
`;

/**
 * Attach shared constants to window._fd so classic-script components
 * (loaded via add_extra_js_url without type="module") can access them.
 * fd-shared-styles.js is always loaded first in LOVELACE_COMPONENTS.
 */
window._fd = {
  escHtml,
  esc,
  eur,
  pct,
  CAT_COLORS,
  CAT_LABELS,
  MEMBER_COLORS,
  MONTH_NAMES,
  SHARED_CSS,
};
