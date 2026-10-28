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
  --r-sm: 4px;
  --r-md: 8px;
  --sh-sm: 0 4px 12px rgba(0,0,0,0.3);
  --sh-md: 0 8px 24px rgba(0,0,0,0.4);
  --sh-lg: 0 20px 60px rgba(0,0,0,0.5);
  --fs-sm: 11px;
  --fs-md: 13px;
  --fs-lg: 18px;
  --fs-xl: 24px;
  --lh-tight: 1;
  --lh-normal: 1.2;
  --sp-xs: 6px;
  --sp-sm: 8px;
  --sp-md: 12px;
  --sp-lg: 18px;
  --sp-xl: 24px;
  /* Design system (round 5). Surfaces, text and accent map onto the HA theme
     variables so light/dark themes keep working; statuses, persons and the
     desktop marker are fixed hues with theme-mixed backgrounds. */
  --fd-page: var(--primary-background-color, #f4f6f8);
  --fd-card: var(--card-background-color, #ffffff);
  --fd-sunk: color-mix(in srgb, var(--fd-t1) 6%, var(--fd-card));
  --fd-line: var(--divider-color, #e6e9ed);
  --fd-t1: var(--primary-text-color, #1b1f24);
  --fd-t2: var(--secondary-text-color, #5b6470);
  --fd-t3: color-mix(in srgb, var(--fd-t2) 70%, var(--fd-card));
  --fd-a500: var(--primary-color, #03a9f4);
  --fd-a700: color-mix(in srgb, var(--fd-a500) 78%, var(--fd-t1));
  --fd-a900: color-mix(in srgb, var(--fd-a500) 55%, var(--fd-t1));
  --fd-a300: color-mix(in srgb, var(--fd-a500) 60%, var(--fd-card));
  --fd-a100: color-mix(in srgb, var(--fd-a500) 28%, var(--fd-card));
  --fd-a50: color-mix(in srgb, var(--fd-a500) 12%, var(--fd-card));
  --fd-ok: #2e7d32;
  --fd-near: #689f38;
  --fd-over: #e65100;
  --fd-ok-bg: color-mix(in srgb, var(--fd-ok) 16%, var(--fd-card));
  --fd-near-bg: color-mix(in srgb, var(--fd-near) 16%, var(--fd-card));
  --fd-over-bg: color-mix(in srgb, var(--fd-over) 16%, var(--fd-card));
  --fd-attn: #ffa000;
  --fd-gold: #f9a825;
  --fd-person-a: #00897b;
  --fd-person-b: #c2185b;
  --fd-household: #0277bd;
  --fd-desktop: #7e57c2;
  --fd-desktop-bg: color-mix(in srgb, var(--fd-desktop) 14%, var(--fd-card));
  --fd-r-card: 14px;
  --fd-r-pill: 999px;
  --fd-sh1: 0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.08);
  --fd-sh2: 0 8px 24px rgba(16,24,40,.16);
  --fd-touch: 44px;
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
/* Global keyboard-focus indicator — applies to every interactive element
   inside the dashboard panel. Removes the dotted browser default in favour
   of a clear, theme-tinted ring. */
button:focus-visible,
a:focus-visible,
[tabindex]:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible,
[role="button"]:focus-visible {
  outline: 2px solid var(--ac);
  outline-offset: 2px;
  border-radius: var(--r-sm);
}
/* Suppress the legacy :focus ring when :focus-visible is supported to avoid
   a doubled outline on mouse clicks. */
button:focus:not(:focus-visible),
a:focus:not(:focus-visible),
[tabindex]:focus:not(:focus-visible) {
  outline: none;
}
/* Scrollbars: styled once, from tokens. */
* { scrollbar-width: thin; scrollbar-color: var(--fd-a100) transparent; }
/* App-styled tooltip (never the native title attribute). data-tip = label
   tier (short delay), data-tip-info = info tier (longer delay). Shown on
   hover and keyboard focus; touch users get the same text as aria-label. */
[data-tip], [data-tip-info] { position: relative; }
[data-tip]::after, [data-tip-info]::after {
  content: attr(data-tip) attr(data-tip-info);
  position: absolute; left: 50%; top: calc(100% + 6px); transform: translateX(-50%);
  z-index: 30; width: max-content; max-width: 240px; padding: 5px 9px;
  border-radius: 8px; font-size: 11.5px; font-weight: 400; line-height: 1.3;
  white-space: normal; text-align: left; pointer-events: none;
  background: var(--fd-card); color: var(--fd-t1);
  border: 1px solid var(--fd-line); border-left: 3px solid var(--fd-a500);
  box-shadow: var(--fd-sh2); opacity: 0; visibility: hidden;
  transition: opacity .12s;
}
@media (hover: hover) {
  [data-tip]:hover::after { opacity: 1; visibility: visible; transition-delay: .35s; }
  [data-tip-info]:hover::after { opacity: 1; visibility: visible; transition-delay: .8s; }
}
[data-tip]:focus-visible::after, [data-tip-info]:focus-visible::after {
  opacity: 1; visibility: visible; transition-delay: .35s;
}
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
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
  const STATIC_BASE = "/finance_dashboard_static";
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

/** Define a custom element unless something already did (reload / double load). */
function defineOnce(name, ctor) {
  if (!customElements.get(name)) customElements.define(name, ctor);
}

/** Add a Lovelace card to the picker exactly once. */
function registerCard(def) {
  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === def.type)) {
    window.customCards.push({ preview: true, ...def });
  }
}

/** Integration page: banks are linked / renewed there (config subentries). */
const INTEGRATION_PATH = "/config/integrations/integration/finance_dashboard";

/**
 * SPA navigation to a HA page (no full reload). Plain clicks are intercepted;
 * ctrl/meta/middle clicks keep the anchor's native behaviour (new tab).
 */
function navigate(path, ev) {
  if (ev && (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button === 1)) return;
  if (ev) ev.preventDefault();
  history.pushState(null, "", path);
  window.dispatchEvent(new CustomEvent("location-changed", { bubbles: true, composed: true }));
}

/** Locale-aware date(+time) for an ISO string; "" when missing/invalid. */
function fmtDate(iso, withTime = false) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const lang = (window._fd && window._fd._hass && window._fd._hass.language)
    || navigator.language || "en";
  return withTime
    ? d.toLocaleString(lang, { dateStyle: "short", timeStyle: "short" })
    : d.toLocaleDateString(lang);
}

/**
 * Attach shared constants to window._fd so classic-script components
 * (loaded via add_extra_js_url without type="module") can access them.
 * fd-shared-styles.js is always loaded first by finance-dashboard-kit.js.
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
  defineOnce,
  registerCard,
  navigate,
  fmtDate,
  INTEGRATION_PATH,
  _hass: null,  // Set by panel shell: window._fd._hass = hass
};

/**
 * Pre-warm locale cache as soon as the script loads so that tSync() calls
 * during first component render already have strings available.
 * Uses navigator.language as initial guess; panel shell updates _hass later.
 */
(function _warmupLocales() {
  const raw = (navigator.language || "en").toLowerCase().split("-")[0];
  const lang = ["de", "en"].includes(raw) ? raw : "en";
  // Fire-and-forget: populate _i18nCache before first render tick
  _loadLocale(lang);
  if (lang !== "en") _loadLocale("en");
})();
