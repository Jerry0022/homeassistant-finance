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
 *   fd-transactions-log  → imported transactions (admin, cache-only)
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
  --dg: var(--error-color, #e74c3c);
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
        if (header.showToast) {
          header.showToast(
            "Tageslimit der Bank-API ist erreicht (4/Tag pro Konto). "
            + "Neue Abfragen sind erst ab morgen 00:00 m\u00f6glich.",
            "warn",
          );
        }
        return;
      }
      if (header) header.refreshing = true;
      if (dp) {
        dp.refresh().finally(() => {
          if (header) header.refreshing = false;
        });
      }
    });

    this.shadowRoot.addEventListener("fd-refresh-done", (e) => {
      const header = this.shadowRoot.querySelector("fd-header");
      if (!header || !header.showToast) return;
      const d = e.detail || {};
      const s = d.status?.stats || {};
      const reason = d.reason || s.outcome || "error";
      if (reason === "ok") {
        const parts = [];
        if (s.accounts) parts.push(`${s.accounts} Konten`);
        if (s.transactions) parts.push(`${s.transactions} Transaktionen`);
        if (s.new) parts.push(`${s.new} neu`);
        const dur = s.duration_ms ? ` in ${(s.duration_ms / 1000).toFixed(1)}s` : "";
        header.showToast(
          `Aktualisiert \u2014 ${parts.join(", ") || "keine Daten"}${dur}`,
          "success",
        );
      } else if (reason === "partial") {
        const msg = `Teilweise aktualisiert \u2014 `
          + `${s.accounts || 0} Konten, ${s.transactions || 0} Tx. `
          + `${(s.errors || []).join(" \u00b7 ")}`.trim();
        header.showToast(msg, "warn");
      } else if (reason === "rate_limited") {
        header.showToast(
          "Tageslimit der Bank-API erreicht. Cache bleibt aktiv, "
          + "neue Live-Daten morgen ab 00:00.",
          "warn",
        );
      } else if (reason === "demo") {
        header.showToast("Demo-Daten neu generiert.", "info");
      } else {
        const errs = (s.errors || []).slice(0, 2).join(" \u00b7 ")
          || "Unbekannter Fehler";
        header.showToast(`Aktualisierung fehlgeschlagen \u2014 ${errs}`, "error");
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

    this.shadowRoot.addEventListener("fd-open-wizard", () => {
      this._openSetupWizard();
    });

    this.shadowRoot.addEventListener("fd-setup-complete", () => {
      // Delay registry refresh — HA reloads the config entry asynchronously
      // after setup/complete (1s deferred_reload in api.py). Wait for it.
      const dp = this.shadowRoot.querySelector("fd-data-provider");
      if (dp) setTimeout(() => dp.refreshRegistry(), 4000);
    });

    this.shadowRoot.addEventListener("fd-setup-closed", () => {
      // Wizard removed itself, nothing extra needed
    });
  }

  _openSetupWizard() {
    // Prevent duplicate wizard
    if (this.shadowRoot.querySelector("fd-setup-wizard")) return;
    const wizard = document.createElement("fd-setup-wizard");
    wizard.hass = this._hass;
    this.shadowRoot.appendChild(wizard);
  }

  _onData(data) {
    const content = this.shadowRoot.getElementById("content");
    if (!content) return;

    // Update header timestamp, rate limit, and demo state
    const header = this.shadowRoot.querySelector("fd-header");
    if (header) {
      header.lastRefresh = data.lastRefresh;
      header.rateLimitedUntil = data.rateLimitedUntil;
      header.lastRefreshStats = data.lastRefreshStats;
      if (data.demoMode !== undefined) header.demoMode = data.demoMode;
    }

    // Loading state (e.g. during demo toggle)
    if (data.loading) return;

    if (data.error) {
      content.className = "error";
      content.innerHTML = `<div>Keine Verbindung m\u00f6glich. <button id="errorWizardBtn" style="background:none;border:none;color:var(--accent-color,#4ecca3);cursor:pointer;text-decoration:underline;font-size:inherit;font-family:inherit;">Bankkonto verbinden</button></div>`;
      content.querySelector("#errorWizardBtn")
        ?.addEventListener("click", () => this._openSetupWizard());
      return;
    }

    // While a refresh is in flight and there's no data yet, keep the
    // user on the "Lade Finanzdaten…" screen instead of flashing
    // the onboarding prompt momentarily.
    if (data.isRefreshing && data.accountCount === 0 && !data.demoMode) {
      content.className = "loading";
      content.innerHTML = "Daten werden geladen\u2026";
      return;
    }

    // Onboarding: no accounts and no demo → show welcome with inline wizard CTA
    if (data.accountCount === 0 && !data.demoMode) {
      content.className = "";
      content.innerHTML = `
<div style="text-align:center;padding:60px 20px;max-width:480px;margin:0 auto;">
  <div style="font-size:48px;margin-bottom:16px;">&#x1F3E6;</div>
  <h2 style="margin:0 0 8px;font-size:20px;font-weight:600;">Willkommen beim Finance Dashboard</h2>
  <p style="color:var(--tx2);margin:0 0 24px;line-height:1.5;">
    Noch keine Bankkonten verbunden. Verbinde jetzt dein Konto oder starte den Demo-Modus.
  </p>
  <button id="onboardingConnectBtn" style="
    padding:12px 28px;border-radius:12px;border:none;
    background:var(--accent-color,#4ecca3);color:var(--primary-background-color,#0a0a0f);font-size:15px;font-weight:700;
    cursor:pointer;font-family:inherit;margin-bottom:12px;
  ">Bankkonto verbinden</button>
  <div style="margin-top:12px;">
    <button id="onboardingDemoBtn" style="
      padding:10px 24px;border-radius:10px;border:2px solid var(--warning-color,#f39c12);
      background:transparent;color:var(--warning-color,#f39c12);font-size:14px;font-weight:600;
      cursor:pointer;font-family:inherit;
    ">Demo starten</button>
  </div>
</div>`;
      content.querySelector("#onboardingConnectBtn")
        .addEventListener("click", () => this._openSetupWizard());
      content.querySelector("#onboardingDemoBtn")
        .addEventListener("click", () => {
          this.shadowRoot.dispatchEvent(new CustomEvent("fd-demo-toggle", {
            bubbles: true,
            composed: true,
          }));
        });
      return;
    }

    // Clear loading state and build component tree
    content.className = "";
    content.innerHTML = "";

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

    // Transaction log (cached, admin-only). Gated inside the component:
    // only renders after at least one bank is linked AND one refresh ran.
    const txLog = document.createElement("fd-transactions-log");
    txLog.data = data;
    content.appendChild(txLog);
  }
}

customElements.define("finance-dashboard-panel", FinanceDashboardPanel);
