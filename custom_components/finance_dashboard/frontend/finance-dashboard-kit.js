/**
 * Finance Dashboard — component kit loader (the ONE entry point of the kit).
 *
 * "One component kit, two shells": every web component (fd-*) and every
 * Lovelace card is defined by this module. The sidebar panel
 * (finance-dashboard-panel.js) is just a full-page layout of the same
 * components; Lovelace cards are the same components in a card frame.
 *
 * Delivery: the integration registers this file with
 * frontend.add_extra_js_url(), so it loads on every dashboard and the cards
 * show up in the card picker with no hand-added Lovelace resource. The panel
 * awaits the same module, so a direct page load of the panel works too.
 *
 * Cache-busting: the integration appends ?v=<VERSION> to this URL. Children
 * are loaded with dynamic import() and inherit that query - static relative
 * imports would drop it and serve stale files from the long-lived cache.
 *
 * Load order: fd-shared-styles first (it defines window._fd, which every other
 * component reads lazily at render time), then everything else in parallel.
 * Nothing here touches ha-card or other HA elements at load time, so the kit
 * can safely run before Lovelace's own elements are defined.
 */

const _query = new URL(import.meta.url).search;
const _load = (file) => import(new URL(file + _query, import.meta.url).href);

const COMPONENTS = [
  "fd-data-provider.js",
  "fd-stat-card.js",
  "fd-person-card.js",
  "fd-donut-chart.js",
  "fd-header.js",
  "fd-stats-row.js",
  "fd-household-section.js",
  "fd-household-cycle.js",
  "fd-freshness.js",
  "fd-budget-plan.js",
  "fd-category-section.js",
  "fd-cost-distribution.js",
  "fd-recurring-list.js",
  "fd-transactions-log.js",
  "fd-settings.js",
  "fd-overview.js",
  "fd-home.js",
  "fd-questions.js",
];

const CARDS = [
  "finance-dashboard-card.js",
  "finance-status-chip.js",
  "fd-budget-config.js",
  "fd-categorize.js",
];

if (!window.__fdKitReady) {
  window.__fdKitReady = (async () => {
    await _load("fd-shared-styles.js");
    await Promise.all([...COMPONENTS, ...CARDS].map(_load));
  })();
}

export const ready = window.__fdKitReady;
await ready;
