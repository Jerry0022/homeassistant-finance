/**
 * fd-cost-distribution — Stacked horizontal bar for cost distribution.
 *
 * Shows category-based cost distribution when no household data is present.
 * (When household is present, the shared costs bar in fd-household-section
 * replaces this view.)
 *
 * Properties:
 *   data {object} — Unified data object from fd-data-provider
 */

// DIST_CAT_COLORS and DIST_CAT_LABELS come from window._fd (set by fd-shared-styles.js).

class FdCostDistribution extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
  }

  set data(v) { this._data = v; this._render(); }

  _render() {
    const d = this._data;
    if (!d) {
      this.shadowRoot.innerHTML = "";
      return;
    }

    // Only show when there's no household shared costs bar
    if (d.household && d.household.total_shared_costs > 0) {
      this.shadowRoot.innerHTML = "";
      return;
    }

    const { CAT_COLORS, CAT_LABELS, SHARED_CSS, escHtml } = window._fd;

    const eur = (v) => new Intl.NumberFormat("de-DE", {
      style: "currency", currency: "EUR",
    }).format(v || 0);

    const cats = d.summary?.categories || {};
    const totalExp = d.summary?.totalExpenses || 0;

    const sorted = Object.entries(cats)
      .filter(([k]) => k !== "income" && k !== "transfers")
      .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));

    const costBar = sorted.map(([cat, amt]) => {
      const p = totalExp > 0 ? Math.abs(amt) / totalExp * 100 : 0;
      return `<div style="width:${p}%;background:${CAT_COLORS[cat] || "#6b7280"}"></div>`;
    }).join("");

    const costLegend = sorted.slice(0, 6).map(([cat, amt]) =>
      `<div class="legend-item">
        <div class="legend-dot" style="background:${CAT_COLORS[cat] || "#6b7280"}"></div>
        ${escHtml(CAT_LABELS[cat] || cat)} ${eur(Math.abs(amt))}
      </div>`
    ).join("");

    const LOCAL_CSS = `
:host {
  margin-bottom: 20px;
}
.cost-bar {
  display: flex;
  height: 10px;
  border-radius: 5px;
  overflow: hidden;
  margin: 12px 0;
}
.cost-bar div { height: 100%; }
.cost-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 0 18px 14px;
  font-size: 11px;
  color: var(--tx2);
}
.legend-item { display: flex; align-items: center; gap: 5px; }
.legend-dot { width: 7px; height: 7px; border-radius: 2px; }
`;

    this.shadowRoot.innerHTML = `
<style>${SHARED_CSS}${LOCAL_CSS}</style>
<div class="card">
  <div class="card-h">Kostenverteilung</div>
  <div style="padding:14px 18px">
    <div class="cost-bar">${costBar || `<div style="width:100%;background:var(--sf2)"></div>`}</div>
  </div>
  <div class="cost-legend">${costLegend}</div>
</div>`;
  }
}

customElements.define("fd-cost-distribution", FdCostDistribution);
