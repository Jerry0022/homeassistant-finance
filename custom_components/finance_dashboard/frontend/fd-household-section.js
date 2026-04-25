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

  disconnectedCallback() {
    // No timers or observers to clean up in this component.
  }

  _render() {
    const d = this._data;
    const household = d?.household;

    if (!household || !household.members || household.members.length === 0) {
      this.shadowRoot.innerHTML = "";
      return;
    }

    const { MEMBER_COLORS, SHARED_CSS, escHtml } = window._fd;

    const eur = (v) => new Intl.NumberFormat("de-DE", {
      style: "currency", currency: "EUR",
    }).format(v || 0);

    const LOCAL_CSS = `
:host {
  margin-bottom: 20px;
}
.persons {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}
@media (max-width: 768px) {
  .persons { grid-template-columns: 1fr; }
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
        return `<div style="width:${w}%;background:${MEMBER_COLORS[i % MEMBER_COLORS.length]}"></div>`;
      }).join("");

      const legend = household.members.map((m, i) =>
        `<div class="legend-item">
          <div class="legend-dot" style="background:${MEMBER_COLORS[i % MEMBER_COLORS.length]}"></div>
          ${escHtml(m.person)} ${eur(m.shared_costs_share)} (${(m.income_ratio || 0).toFixed(0)}%)
        </div>`
      ).join("");

      sharedEl.innerHTML = `
<div class="card">
  <div class="card-h">Geteilte Fixkosten
    <span style="font-weight:400;font-size:12px;color:var(--tx2)">${eur(household.total_shared_costs)} gesamt</span>
  </div>
  <div style="padding:14px 18px">
    <div class="cost-bar">${barSegments}</div>
  </div>
  <div class="cost-legend">${legend}</div>
</div>`;
    }
  }
}

customElements.define("fd-household-section", FdHouseholdSection);
