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

const DIST_CAT_COLORS = {
  housing: "#3b82f6", loans: "#e74c3c", food: "#f97316", utilities: "#eab308",
  insurance: "#8b5cf6", subscriptions: "#ec4899", transport: "#06b6d4",
  cleaning: "#a855f7", income: "#4ecca3", transfers: "#6b7280", other: "#6b7280",
};
const DIST_CAT_LABELS = {
  housing: "Wohnen", loans: "Kredite", food: "Lebensmittel", utilities: "Nebenkosten",
  insurance: "Versicherung", subscriptions: "Abos", transport: "Mobilit\u00e4t",
  cleaning: "Reinigung", income: "Einkommen", transfers: "\u00dcbertr\u00e4ge", other: "Sonstiges",
};

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
      return `<div style="width:${p}%;background:${DIST_CAT_COLORS[cat] || "#6b7280"}"></div>`;
    }).join("");

    const costLegend = sorted.slice(0, 6).map(([cat, amt]) =>
      `<div class="legend-item">
        <div class="legend-dot" style="background:${DIST_CAT_COLORS[cat] || "#6b7280"}"></div>
        ${this._esc(DIST_CAT_LABELS[cat] || cat)} ${eur(Math.abs(amt))}
      </div>`
    ).join("");

    this.shadowRoot.innerHTML = `
<style>
:host {
  --sf: var(--card-background-color, #12121a);
  --sf2: #1a1a28;
  --bd: rgba(255,255,255,0.06);
  --tx2: var(--secondary-text-color, #9898a8);
  --r: 14px;
  display: block;
  margin-bottom: 20px;
}
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
</style>
<div class="card">
  <div class="card-h">Kostenverteilung</div>
  <div style="padding:14px 18px">
    <div class="cost-bar">${costBar || `<div style="width:100%;background:var(--sf2)"></div>`}</div>
  </div>
  <div class="cost-legend">${costLegend}</div>
</div>`;
  }

  _esc(s) {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }
}

customElements.define("fd-cost-distribution", FdCostDistribution);
