/**
 * Finance Dashboard — Sidebar Panel Shell
 *
 * Thin orchestrator that wires together the component tree:
 *   fd-data-provider  → entity subscription + API bridge
 *   fd-header         → title bar, month selector, refresh
 *   fd-stats-row      → 4 KPI cards (balance, expenses, income, savings)
 *   fd-household-section → person cards + shared costs (conditional)
 *   fd-category-section  → donut chart + top-3 + fix/var
 *   fd-cost-distribution → category cost bar (when no household)
 *   fd-recurring-list    → recurring payments
 *
 * Data flow: fd-data-provider reads HA entities + one API call,
 * dispatches "fd-data-updated" → shell pushes data to all children.
 *
 * See docs/ARCHITECTURE-FRONTEND.md for full architecture documentation.
 */

class FinanceDashboardPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._rendered = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._rendered) {
      this._render();
      this._rendered = true;
    }
    // Forward hass to data provider (drives entity subscriptions)
    const dp = this.shadowRoot.querySelector("fd-data-provider");
    if (dp) dp.hass = hass;
  }

  _render() {
    this.shadowRoot.innerHTML = `
<style>
:host {
  --bg: var(--primary-background-color, #0a0a0f);
  --tx: var(--primary-text-color, #e0e0e0);
  --tx2: var(--secondary-text-color, #9898a8);
  --dg: #e74c3c;
  display: block;
  font-family: 'Segoe UI', system-ui, sans-serif;
  background: var(--bg);
  color: var(--tx);
  min-height: 100vh;
}
.fd {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}
.loading {
  text-align: center;
  padding: 60px;
  color: var(--tx2);
}
.error {
  text-align: center;
  padding: 40px;
  color: var(--dg);
}
</style>

<fd-data-provider></fd-data-provider>
<div class="fd">
  <fd-header></fd-header>
  <div id="content" class="loading">Lade Finanzdaten\u2026</div>
</div>`;

    // Wire events
    this.shadowRoot.addEventListener("fd-data-updated", (e) => {
      this._onData(e.detail);
    });

    this.shadowRoot.addEventListener("fd-refresh-requested", () => {
      const dp = this.shadowRoot.querySelector("fd-data-provider");
      const header = this.shadowRoot.querySelector("fd-header");
      // Don't call the API if rate-limited — button should already be disabled,
      // but guard here as well.
      if (header && header._rateLimitedUntil &&
          new Date(header._rateLimitedUntil) > new Date()) {
        return;
      }
      if (header) header.refreshing = true;
      if (dp) {
        dp.refresh().finally(() => {
          if (header) header.refreshing = false;
        });
      }
    });

    this.shadowRoot.addEventListener("fd-demo-toggle", () => {
      const dp = this.shadowRoot.querySelector("fd-data-provider");
      const header = this.shadowRoot.querySelector("fd-header");
      if (dp) {
        dp.toggleDemo().then((enabled) => {
          if (header) header.demoMode = enabled;
        });
      }
    });
  }

  _onData(data) {
    const content = this.shadowRoot.getElementById("content");
    if (!content) return;

    if (data.error) {
      content.className = "error";
      content.innerHTML = `<div>Verbinde dein Bankkonto unter Einstellungen \u2192 Integrationen \u2192 Finance.</div>`;
      return;
    }

    // Clear loading state and build component tree
    content.className = "";
    content.innerHTML = "";

    // Update header timestamp, rate limit, and demo state
    const header = this.shadowRoot.querySelector("fd-header");
    if (header) {
      header.lastRefresh = data.lastRefresh;
      header.rateLimitedUntil = data.rateLimitedUntil;
      if (data.demoMode !== undefined) header.demoMode = data.demoMode;
    }

    // Stats row
    const statsRow = document.createElement("fd-stats-row");
    statsRow.data = data;
    content.appendChild(statsRow);

    // Household section (conditional — only if household data present)
    const household = document.createElement("fd-household-section");
    household.data = data;
    content.appendChild(household);

    // Category section (donut + top-3 + fix/var)
    const category = document.createElement("fd-category-section");
    category.data = data;
    content.appendChild(category);

    // Cost distribution (only visible when no household shared costs)
    const costDist = document.createElement("fd-cost-distribution");
    costDist.data = data;
    content.appendChild(costDist);

    // Recurring payments
    const recurring = document.createElement("fd-recurring-list");
    recurring.data = data;
    content.appendChild(recurring);
  }
}

customElements.define("finance-dashboard-panel", FinanceDashboardPanel);
