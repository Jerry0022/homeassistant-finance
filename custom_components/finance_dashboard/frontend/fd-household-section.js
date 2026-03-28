/**
 * fd-household-section — Person cards + shared costs distribution bar.
 *
 * Renders conditionally: only visible when household data is present.
 *
 * Properties:
 *   data {object} — Unified data object from fd-data-provider
 */

class FdHouseholdSection extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
  }

  set data(v) { this._data = v; this._render(); }

  _render() {
    const d = this._data;
    const household = d?.household;

    if (!household || !household.members || household.members.length === 0) {
      this.shadowRoot.innerHTML = "";
      return;
    }

    const eur = (v) => new Intl.NumberFormat("de-DE", {
      style: "currency", currency: "EUR",
    }).format(v || 0);

    const memberColors = ["#3b82f6", "#8b5cf6", "#f97316", "#ec4899", "#06b6d4"];

    this.shadowRoot.innerHTML = `
<style>
:host { display: block; margin-bottom: 20px; }
.persons {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}
@media (max-width: 768px) {
  .persons { grid-template-columns: 1fr; }
}
.card {
  background: var(--card-background-color, #12121a);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 14px;
}
.card-h {
  padding: 14px 18px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  font-size: 14px;
  font-weight: 600;
  display: flex;
  justify-content: space-between;
  align-items: center;
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
  color: var(--secondary-text-color, #9898a8);
}
.legend-item { display: flex; align-items: center; gap: 5px; }
.legend-dot { width: 7px; height: 7px; border-radius: 2px; }
</style>

<div class="persons" id="persons"></div>
<div id="shared"></div>`;

    // Create person cards
    const personsEl = this.shadowRoot.getElementById("persons");
    for (const m of household.members) {
      const card = document.createElement("fd-person-card");
      card.member = m;
      card.splitModel = household.split_model || "proportional";
      personsEl.appendChild(card);
    }

    // Shared costs bar
    const sharedEl = this.shadowRoot.getElementById("shared");
    if (household.total_shared_costs > 0) {
      const barSegments = household.members.map((m, i) => {
        const w = household.total_shared_costs > 0
          ? (m.shared_costs_share / household.total_shared_costs * 100)
          : 0;
        return `<div style="width:${w}%;background:${memberColors[i % memberColors.length]}"></div>`;
      }).join("");

      const legend = household.members.map((m, i) =>
        `<div class="legend-item">
          <div class="legend-dot" style="background:${memberColors[i % memberColors.length]}"></div>
          ${this._esc(m.person)} ${eur(m.shared_costs_share)} (${(m.income_ratio || 0).toFixed(0)}%)
        </div>`
      ).join("");

      sharedEl.innerHTML = `
<div class="card">
  <div class="card-h">Geteilte Fixkosten
    <span style="font-weight:400;font-size:12px;color:var(--secondary-text-color, #9898a8)">${eur(household.total_shared_costs)} gesamt</span>
  </div>
  <div style="padding:14px 18px">
    <div class="cost-bar">${barSegments}</div>
  </div>
  <div class="cost-legend">${legend}</div>
</div>`;
    }
  }

  _esc(s) {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }
}

customElements.define("fd-household-section", FdHouseholdSection);
