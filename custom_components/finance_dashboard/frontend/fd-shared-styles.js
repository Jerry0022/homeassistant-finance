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
 * i18n helper — lazy-loads locale JSON and resolves keys with placeholder substitution.
 *
 * Usage:
 *   await window._fd.t("header.refresh.button")
 *   await window._fd.t("header.refresh.toast_success", { accounts: 3, tx: 50, new: 2, duration: "1.2s" })
 *
 * Language resolution order:
 *   1. hass.language (if hass is provided via window._fd._hass)
 *   2. navigator.language
 *   3. Fallback: "en"
 *
 * Supported languages: "de", "en". Unknown languages fall back to "en".
 */
const _i18nCache = {};

async function _loadLocale(lang) {
  if (_i18nCache[lang]) return _i18nCache[lang];
  const STATIC_BASE = "/api/finance_dashboard/static";
  try {
    const resp = await fetch(`${STATIC_BASE}/locales/${lang}.json`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    _i18nCache[lang] = await resp.json();
  } catch (_) {
    _i18nCache[lang] = null;
  }
  return _i18nCache[lang];
}

function _resolveLang() {
  const hassLang = window._fd && window._fd._hass && window._fd._hass.language;
  const raw = hassLang || navigator.language || "en";
  const base = raw.toLowerCase().split("-")[0];
  return ["de", "en"].includes(base) ? base : "en";
}

/**
 * Translate a key with optional variable substitution.
 * Variables replace $key occurrences in the string.
 * Synchronously returns the key as fallback if locale is not yet loaded.
 */
async function t(key, vars = {}) {
  const lang = _resolveLang();
  let strings = await _loadLocale(lang);
  if (!strings || !strings[key]) {
    if (lang !== "en") strings = await _loadLocale("en");
  }
  let text = (strings && strings[key]) ? strings[key] : key;
  for (const [k, v] of Object.entries(vars)) {
    text = text.replace(new RegExp(`\\$${k}`, "g"), String(v));
  }
  return text;
}

/**
 * Synchronous translation — returns cached value or key as fallback.
 * Pre-warm the cache by calling t() once during component init.
 */
function tSync(key, vars = {}) {
  const lang = _resolveLang();
  const strings = _i18nCache[lang] || _i18nCache["en"] || {};
  let text = strings[key] || key;
  for (const [k, v] of Object.entries(vars)) {
    text = text.replace(new RegExp(`\\$${k}`, "g"), String(v));
  }
  return text;
}

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
  t,
  tSync,
  _hass: null,  // Set by panel shell: window._fd._hass = hass
};
