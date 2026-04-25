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
 * A3: Components are created once in _ensureComponents() and persist
 * across fd-data-updated events. Only .data properties are updated,
 * never the component tree itself. Loading/error/onboarding states
 * use a #overlay div toggled with .hidden instead of innerHTML teardown.
 *
 * See docs/ARCHITECTURE-FRONTEND.md for full architecture documentation.
 */

class FinanceDashboardPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._rendered = false;
    // Persistent component references (A3)
    this._statsRow = null;
    this._household = null;
    this._category = null;
    this._costDist = null;
    this._recurring = null;
    this._txLog = null;
    this._overlay = null;
    this._overlayState = null; // "loading" | "refreshing" | "error" | "onboarding" | null
    this._onboardingConnected = false;
  }

  set hass(hass) {
    this._hass = hass;
    // Expose hass for i18n language detection
    if (window._fd) window._fd._hass = hass;
    if (!this._rendered) {
      this._render();
      this._rendered = true;
      // Dismiss setup-complete notification on first panel load
      this._dismissSetupNotification(hass);
    }
    // Forward hass to data provider (drives entity subscriptions)
    const dp = this.shadowRoot.querySelector("fd-data-provider");
    if (dp) dp.hass = hass;
  }

  _dismissSetupNotification(hass) {
    if (!hass) return;
    hass.callService("persistent_notification", "dismiss", {
      notification_id: "fd_setup_complete",
    }).catch(() => {
      // Notification may not exist — silently ignore
    });
  }

  _render() {
    const { tSync } = window._fd;
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
/* Overlay covers the component tree for transient states */
#overlay { display: block; }
#overlay.hidden { display: none; }
/* Component tree is hidden while overlay is shown */
#components { display: block; }
#components.hidden { display: none; }
</style>

<fd-data-provider></fd-data-provider>
<div class="fd">
  <fd-header></fd-header>
  <div id="overlay" class="loading">${tSync("panel.loading")}</div>
  <div id="components" class="hidden"></div>
</div>`;

    this._overlay = this.shadowRoot.getElementById("overlay");

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
            window._fd.tSync("header.refresh.toast_rate_limited"),
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
      const { tSync } = window._fd;
      const d = e.detail || {};
      const s = d.status?.stats || {};
      const reason = d.reason || s.outcome || "error";
      if (reason === "ok") {
        const parts = [];
        if (s.accounts) parts.push(`${s.accounts} ${tSync("general.accounts_plural")}`);
        if (s.transactions) parts.push(`${s.transactions} ${tSync("general.transactions")}`);
        if (s.new) parts.push(`${s.new} ${tSync("general.new")}`);
        const dur = s.duration_ms ? ` in ${(s.duration_ms / 1000).toFixed(1)}s` : "";
        header.showToast(
          `${tSync("panel.loading.refresh").replace(/…$/, "")} — ${parts.join(", ") || tSync("transactions.empty")}${dur}`,
          "success",
        );
      } else if (reason === "partial") {
        const msg = `${tSync("general.partial_error")} — `
          + `${s.accounts || 0} ${tSync("general.accounts_plural")}, ${s.transactions || 0} Tx. `
          + `${(s.errors || []).join(" · ")}`.trim();
        header.showToast(msg, "warn");
      } else if (reason === "rate_limited") {
        header.showToast(
          tSync("header.refresh.toast_rate_limited"),
          "warn",
        );
      } else if (reason === "demo") {
        header.showToast(tSync("toast.demo_started"), "info");
      } else {
        const errs = (s.errors || []).slice(0, 2).join(" · ")
          || tSync("general.error");
        header.showToast(`${tSync("general.error")} — ${errs}`, "error");
      }
    });

    this.shadowRoot.addEventListener("fd-demo-toggle", () => {
      const dp = this.shadowRoot.querySelector("fd-data-provider");
      const header = this.shadowRoot.querySelector("fd-header");
      if (dp) {
        dp.toggleDemo().then((enabled) => {
          if (header) header.demoMode = enabled;
          if (header && header.showToast) {
            header.showToast(
              window._fd.tSync(enabled ? "toast.demo_started" : "toast.demo_stopped"),
              "info",
            );
          }
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

  /**
   * A3: Create the persistent component tree once.
   * Subsequent calls are no-ops.
   */
  _ensureComponents() {
    if (this._statsRow) return; // already created

    const container = this.shadowRoot.getElementById("components");

    this._statsRow = document.createElement("fd-stats-row");
    container.appendChild(this._statsRow);

    this._household = document.createElement("fd-household-section");
    container.appendChild(this._household);

    this._category = document.createElement("fd-category-section");
    container.appendChild(this._category);

    this._costDist = document.createElement("fd-cost-distribution");
    container.appendChild(this._costDist);

    this._recurring = document.createElement("fd-recurring-list");
    container.appendChild(this._recurring);

    // Transaction log (cached, admin-only). Gated inside the component:
    // only renders after at least one bank is linked AND one refresh ran.
    this._txLog = document.createElement("fd-transactions-log");
    container.appendChild(this._txLog);
  }

  /** Show overlay with a given state; hide component tree. */
  _showOverlay(state, html) {
    this._overlayState = state;
    const overlay = this._overlay;
    const components = this.shadowRoot.getElementById("components");
    if (!overlay) return;
    overlay.className = state === "error" ? "error" : "loading";
    overlay.innerHTML = html;
    overlay.classList.remove("hidden");
    if (components) components.classList.add("hidden");
  }

  /** Hide overlay; show component tree. */
  _hideOverlay() {
    this._overlayState = null;
    const overlay = this._overlay;
    const components = this.shadowRoot.getElementById("components");
    if (overlay) overlay.classList.add("hidden");
    if (components) components.classList.remove("hidden");
  }

  async _openSetupWizard() {
    // Prevent duplicate wizard
    if (this.shadowRoot.querySelector("fd-setup-wizard")) return;
    const wizard = document.createElement("fd-setup-wizard");
    wizard.hass = this._hass;

    // If credentials are already present (existing integration), start at step 1
    // (institution selection) — credentials are reused automatically by the backend.
    // Check /setup/auth_status to determine if setup has already been performed.
    // Default to step 1 (safe fallback).
    let startStep = 1;
    if (this._hass) {
      try {
        const status = await this._hass.callApi("GET", "finance_dashboard/setup/status");
        // If we already have credentials stored (any account configured or setup started),
        // open directly at institution selection (step 1 — credentials flow is in HA config flow).
        // Status "ready" or "configured" means creds exist → skip nothing, wizard starts at step 1.
        // We set initialStep=1 unconditionally here — the wizard always starts at institution list
        // when called from "+ Konto" since credentials are already stored in the integration.
        startStep = 1;
      } catch (_) {
        startStep = 1;
      }
    }
    wizard.initialStep = startStep;
    this.shadowRoot.appendChild(wizard);
  }

  _onData(data) {
    const { tSync } = window._fd;

    // Update header timestamp, rate limit, and demo state
    const header = this.shadowRoot.querySelector("fd-header");
    if (header) {
      header.lastRefresh = data.lastRefresh;
      header.rateLimitedUntil = data.rateLimitedUntil;
      header.lastRefreshStats = data.lastRefreshStats;
      if (data.demoMode !== undefined) header.demoMode = data.demoMode;
    }

    // Loading state (e.g. during demo toggle)
    if (data.loading) {
      this._showOverlay("loading", tSync("panel.loading"));
      return;
    }

    if (data.error) {
      this._showOverlay("error",
        `<div>${tSync("panel.error")} <button id="errorWizardBtn" style="background:none;border:none;color:var(--accent-color,#4ecca3);cursor:pointer;text-decoration:underline;font-size:inherit;font-family:inherit;">${tSync("panel.error.connect")}</button></div>`);
      this._overlay.querySelector("#errorWizardBtn")
        ?.addEventListener("click", () => this._openSetupWizard());
      return;
    }

    // While a refresh is in flight and there's no data yet, keep the
    // user on the loading screen instead of flashing the onboarding
    // prompt momentarily.
    if (data.isRefreshing && data.accountCount === 0 && !data.demoMode) {
      this._showOverlay("loading", tSync("panel.loading.refresh"));
      return;
    }

    // Onboarding: no accounts and no demo → show welcome with inline wizard CTA
    if (data.accountCount === 0 && !data.demoMode) {
      const needsRebind = this._overlayState !== "onboarding";
      this._showOverlay("onboarding", `
<div style="text-align:center;padding:60px 20px;max-width:480px;margin:0 auto;">
  <div style="font-size:48px;margin-bottom:16px;">&#x1F3E6;</div>
  <h2 style="margin:0 0 8px;font-size:20px;font-weight:600;">${tSync("panel.onboarding.title")}</h2>
  <p style="color:var(--tx2);margin:0 0 24px;line-height:1.5;">
    ${tSync("panel.onboarding.body")}
  </p>
  <button id="onboardingConnectBtn" style="
    padding:12px 28px;border-radius:12px;border:none;
    background:var(--accent-color,#4ecca3);color:var(--primary-background-color,#0a0a0f);font-size:15px;font-weight:700;
    cursor:pointer;font-family:inherit;margin-bottom:12px;
  ">${tSync("panel.onboarding.cta_link")}</button>
  <div style="margin-top:12px;">
    <button id="onboardingDemoBtn" style="
      padding:10px 24px;border-radius:10px;border:2px solid var(--warning-color,#f39c12);
      background:transparent;color:var(--warning-color,#f39c12);font-size:14px;font-weight:600;
      cursor:pointer;font-family:inherit;
    ">${tSync("panel.onboarding.cta_demo")}</button>
  </div>
</div>`);
      if (needsRebind) {
        // Only bind event listeners when we freshly entered the onboarding state.
        // _showOverlay() rebuilds innerHTML so listeners must be re-attached.
        this._overlay.querySelector("#onboardingConnectBtn")
          ?.addEventListener("click", () => this._openSetupWizard());
        this._overlay.querySelector("#onboardingDemoBtn")
          ?.addEventListener("click", () => {
            this.shadowRoot.dispatchEvent(new CustomEvent("fd-demo-toggle", {
              bubbles: true,
              composed: true,
            }));
          });
      }
      return;
    }

    // Data available: ensure persistent components exist and push new data.
    this._ensureComponents();
    this._hideOverlay();

    this._statsRow.data = data;
    this._household.data = data;
    this._category.data = data;
    this._costDist.data = data;
    this._recurring.data = data;
    this._txLog.data = data;
  }
}

customElements.define("finance-dashboard-panel", FinanceDashboardPanel);
