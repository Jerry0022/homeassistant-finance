/**
 * Finance Dashboard — Sidebar Panel Shell
 *
 * Two tabs:
 *   Übersicht / Overview  fd-overview   plain facts (accounts, bank status,
 *                                       admin transaction list). Always on.
 *   Haushalt / Household  the household / budget-plan component tree.
 *                         Only when the integration option `show_household`
 *                         is on (GET finance_dashboard/settings, default on).
 *
 * The Refresh button lives in fd-header; this shell performs the attended
 * POST finance_dashboard/refresh itself (the backend derives the PSU headers
 * from this very HTTP request) and then reloads whatever is on screen.
 *
 * Household data flow: fd-data-provider reads HA entities + one API call and
 * dispatches "fd-data-updated" -> shell pushes data into the persistent
 * components (A3: created once, only .data changes afterwards). The provider
 * is only activated when the household tab is enabled or demo mode is used.
 *
 * Banks are linked in the HA integration page (config subentries); every
 * "add bank" entry point here navigates there.
 *
 * See docs/ARCHITECTURE-FRONTEND.md for full architecture documentation.
 */

// One kit, two shells: load the shared components before defining the shell.
// Same ?v= query as this module, so the kit instance is shared and cache-busted.
await import(new URL("finance-dashboard-kit.js" + new URL(import.meta.url).search, import.meta.url).href);

const DOMAIN = "finance_dashboard";

class FinanceDashboardPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._rendered = false;
    // Persistent household component references (A3)
    this._statsRow = null;
    this._household = null;
    this._category = null;
    this._costDist = null;
    this._recurring = null;
    this._budgetPlan = null;
    this._overlay = null;
    this._overlayState = null; // "loading" | "refreshing" | "error" | "onboarding" | null
    this._showHousehold = false;
    this._dpActive = false;
    this._tab = "overview";
    this._refreshing = false;
  }

  set hass(hass) {
    this._hass = hass;
    // Expose hass for i18n language detection
    if (window._fd) window._fd._hass = hass;
    if (!this._rendered) {
      if (!this._rendering) {
        this._rendering = true;
        // Load the user's locale first so the very first render is translated.
        window._fd.t("panel.loading").finally(() => {
          this._render();
          this._rendered = true;
          // Dismiss setup-complete notification on first panel load
          this._dismissSetupNotification(this._hass);
          this._init();
          this.hass = this._hass;
        });
      }
      return;
    }
    const ov = this.shadowRoot.querySelector("fd-overview");
    if (ov) ov.hass = hass;
    // Forward hass to the data provider only while the household side is live
    // (it subscribes to the entity registry and reads entity states).
    if (this._dpActive) {
      const dp = this.shadowRoot.querySelector("fd-data-provider");
      if (dp) dp.hass = hass;
      if (this._budgetPlan && !this._budgetPlan.hass) this._budgetPlan.hass = hass;
    }
  }

  async _init() {
    await this._loadSettings();
    await this._loadHeaderStatus();
    this._maybeAutoRefresh();
  }

  /** Read panel options; a failure keeps the household features on (default). */
  async _loadSettings() {
    let show = true;
    try {
      const s = await this._hass.callApi("GET", `${DOMAIN}/settings`);
      if (s && typeof s.show_household === "boolean") show = s.show_household;
    } catch (e) {
      // Older backend or transient error: keep the default.
    }
    this._setHouseholdEnabled(show);
  }

  _setHouseholdEnabled(enabled) {
    this._showHousehold = enabled;
    if (enabled) this._activateProvider();
    this._updateTabs();
  }

  _activateProvider() {
    if (this._dpActive || !this._hass) return;
    this._dpActive = true;
    const dp = this.shadowRoot.querySelector("fd-data-provider");
    if (dp) dp.hass = this._hass;
    if (this._budgetPlan) this._budgetPlan.hass = this._hass;
  }

  /** Household tab is offered when enabled, or while demo mode is on. */
  get _householdVisible() {
    const dp = this.shadowRoot.querySelector("fd-data-provider");
    return this._showHousehold || !!(dp && dp.demoMode);
  }

  _updateTabs() {
    const sh = this.shadowRoot;
    const bar = sh.getElementById("tabs");
    if (!bar) return;
    const visible = this._householdVisible;
    bar.hidden = !visible;
    if (!visible && this._tab === "household") this._selectTab("overview");
    else this._selectTab(this._tab);
  }

  _selectTab(tab) {
    const sh = this.shadowRoot;
    this._tab = tab;
    for (const b of sh.querySelectorAll("#tabs [role=tab]")) {
      const on = b.dataset.tab === tab;
      b.setAttribute("aria-selected", String(on));
      b.tabIndex = on ? 0 : -1;
    }
    sh.getElementById("viewOverview").hidden = tab !== "overview";
    sh.getElementById("viewHousehold").hidden = tab !== "household";
  }

  /**
   * Fetch live data once when the panel opens and the cache has aged out.
   *
   * The user opening the dashboard IS the session, so the backend attaches
   * PSU headers and the call counts as attended - PSD2 RTS Art. 36(5)(b)
   * caps only unattended access, which is why this does not eat into the
   * 4/day budget the way the scheduled 06:30 fetch does.
   *
   * Fires at most once per panel mount, only for admins (the endpoint is
   * admin-only) and only above the configured age threshold. This is a user
   * action, not an interval - no polling.
   */
  async _maybeAutoRefresh() {
    if (!this._hass || !this._hass.user || !this._hass.user.is_admin) return;
    try {
      const status = await this._hass.callApi("GET", `${DOMAIN}/refresh_status`);
      if (!status || status.auto_refresh_on_open === false) return;
      if (status.demo_mode || status.is_refreshing) return;
      if (!status.account_count) return;

      const maxAge = status.auto_refresh_max_age_seconds;
      if (!maxAge) return;
      const age = status.cache_age_seconds;
      // A never-refreshed cache (null) is maximally stale - fetch it.
      if (age !== null && age !== undefined && age < maxAge) return;

      this.shadowRoot.dispatchEvent(new CustomEvent("fd-refresh-requested", { bubbles: false }));
    } catch (e) {
      // Best effort: the panel is fully usable from cache without this.
    }
  }

  /** Header timestamp / rate-limit chip from the cache-only status endpoint. */
  async _loadHeaderStatus() {
    if (!this._hass) return;
    try {
      const s = await this._hass.callApi("GET", `${DOMAIN}/refresh_status`);
      this._applyStatusToHeader(s);
    } catch (e) {
      // Cosmetic only.
    }
  }

  _applyStatusToHeader(s) {
    const header = this.shadowRoot.querySelector("fd-header");
    if (!header || !s) return;
    header.lastRefresh = s.last_refresh || null;
    header.rateLimitedUntil = s.rate_limited_until || null;
    header.lastRefreshStats = s.stats || null;
  }

  _dismissSetupNotification(hass) {
    if (!hass) return;
    hass.callService("persistent_notification", "dismiss", {
      notification_id: "fd_setup_complete",
    }).catch(() => {
      // Notification may not exist - silently ignore
    });
  }

  _render() {
    const { tSync } = window._fd;
    this.shadowRoot.innerHTML = `
<style>
:host {
  --bg: var(--primary-background-color, #0a0a0f);
  --sf: var(--card-background-color, #12121a);
  --bd: rgba(255,255,255,0.06);
  --tx: var(--primary-text-color, #e0e0e0);
  --tx2: var(--secondary-text-color, #9898a8);
  --ac: var(--accent-color, #4ecca3);
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
[hidden] { display: none !important; }
.tabs {
  display: flex;
  gap: 4px;
  margin: 0 0 var(--sp-xl, 24px);
  border-bottom: 1px solid var(--bd);
}
.tabs button {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--tx2);
  padding: 8px 16px;
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
}
.tabs button:hover { color: var(--tx); }
.tabs button[aria-selected="true"] { color: var(--ac); border-bottom-color: var(--ac); font-weight: 600; }
.tabs button:focus-visible { outline: 2px solid var(--ac); outline-offset: 2px; border-radius: 4px; }
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
  <div class="tabs" id="tabs" role="tablist" aria-label="${tSync("tabs.label")}" hidden>
    <button role="tab" data-tab="overview" aria-selected="true">${tSync("tabs.overview")}</button>
    <button role="tab" data-tab="household" aria-selected="false" tabindex="-1">${tSync("tabs.household")}</button>
  </div>
  <div id="viewOverview" role="tabpanel"><fd-overview></fd-overview></div>
  <div id="viewHousehold" role="tabpanel" hidden>
    <div id="overlay" class="loading">${tSync("panel.loading")}</div>
    <div id="components" class="hidden"></div>
  </div>
</div>`;

    this._overlay = this.shadowRoot.getElementById("overlay");
    const sh = this.shadowRoot;

    // Tabs: click + arrow-key navigation
    const tabs = sh.getElementById("tabs");
    tabs.addEventListener("click", (e) => {
      const b = e.target.closest("[role=tab]");
      if (b) this._selectTab(b.dataset.tab);
    });
    tabs.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      const order = [...tabs.querySelectorAll("[role=tab]")];
      const next = order[(order.findIndex((b) => b.dataset.tab === this._tab) + (e.key === "ArrowRight" ? 1 : -1) + order.length) % order.length];
      this._selectTab(next.dataset.tab);
      next.focus();
    });

    sh.addEventListener("fd-data-updated", (e) => this._onData(e.detail));

    sh.addEventListener("fd-refresh-requested", () => this._refresh());

    // dp-initiated refreshes (demo mode) report through this event.
    sh.addEventListener("fd-refresh-done", (e) => this._toastRefresh(e.detail || {}));

    sh.addEventListener("fd-demo-toggle", async () => {
      const dp = sh.querySelector("fd-data-provider");
      const header = sh.querySelector("fd-header");
      if (!dp) return;
      this._dpActive = true;
      if (this._hass) dp.hass = this._hass;
      const enabled = await dp.toggleDemo();
      if (header) {
        header.demoMode = enabled;
        if (header.showToast) {
          header.showToast(window._fd.tSync(enabled ? "toast.demo_started" : "toast.demo_stopped"), "info");
        }
      }
      // Demo data only exists on the household side: show it there.
      this._updateTabs();
      if (enabled) this._selectTab("household");
      else if (!this._showHousehold) this._dpActive = false;
    });
  }

  /**
   * One attended live refresh. The button is the user's action, so the
   * backend sends PSU headers (never gated on the unattended 4/day cap).
   * A debounced or blocked answer is reported, not retried.
   */
  async _refresh() {
    if (this._refreshing || !this._hass) return;
    const sh = this.shadowRoot;
    const header = sh.querySelector("fd-header");
    const dp = sh.querySelector("fd-data-provider");
    this._refreshing = true;
    if (header) header.refreshing = true;
    try {
      if (dp && dp.demoMode) {
        await dp.refresh();
        return;
      }
      let detail;
      try {
        const resp = await this._hass.callApi("POST", `${DOMAIN}/refresh`);
        const status = resp && resp.status;
        detail = {
          status,
          ok: !!(resp && resp.ok),
          reason: resp && resp.ok === false
            ? (resp.reason || "error")
            : (status && status.stats && status.stats.outcome) || "ok",
        };
        if (resp && resp.message) detail.message = resp.message;
        this._applyStatusToHeader(status);
      } catch (e) {
        const denied = e && (e.status_code === 403 || (e.body && e.body.error === "admin_required"));
        detail = { ok: false, reason: denied ? "admin_required" : "error" };
      }
      this._toastRefresh(detail);
      const ov = sh.querySelector("fd-overview");
      if (ov) ov.reload();
      if (this._dpActive && dp) dp.rebuildAfterRefresh();
    } finally {
      this._refreshing = false;
      if (header) header.refreshing = false;
    }
  }

  _toastRefresh(d) {
    const header = this.shadowRoot.querySelector("fd-header");
    if (!header || !header.showToast) return;
    const { tSync } = window._fd;
    const s = (d.status && d.status.stats) || {};
    const reason = d.reason || s.outcome || "error";
    if (reason === "ok") {
      const parts = [];
      if (s.accounts) parts.push(`${s.accounts} ${tSync("general.accounts_plural")}`);
      if (s.transactions) parts.push(`${s.transactions} ${tSync("general.transactions")}`);
      if (s.new) parts.push(`${s.new} ${tSync("general.new")}`);
      const dur = s.duration_ms ? ` · ${(s.duration_ms / 1000).toFixed(1)}s` : "";
      header.showToast(
        `${tSync("panel.loading.refresh").replace(/…$/, "")} — ${parts.join(", ") || tSync("transactions.empty")}${dur}`,
        "success",
      );
    } else if (reason === "partial") {
      const msg = `${tSync("general.partial_error")} — `
        + `${s.accounts || 0} ${tSync("general.accounts_plural")}, ${s.transactions || 0} Tx. `
        + `${(s.errors || []).join(" · ")}`.trim();
      header.showToast(msg, "warn");
    } else if (reason === "debounced") {
      header.showToast(tSync("header.refresh.toast_debounced"), "info");
    } else if (reason === "rate_limited") {
      header.showToast(tSync("header.refresh.toast_rate_limited"), "warn");
    } else if (reason === "admin_required") {
      header.showToast(tSync("header.refresh.toast_admin"), "warn");
    } else if (reason === "demo") {
      header.showToast(tSync("toast.demo_started"), "info");
    } else {
      const errs = (s.errors || []).slice(0, 2).join(" · ") || tSync("general.error");
      header.showToast(`${tSync("general.error")} — ${errs}`, "error");
    }
  }

  /**
   * A3: Create the persistent household component tree once.
   * Subsequent calls are no-ops.
   */
  _ensureComponents() {
    if (this._statsRow) return; // already created

    const container = this.shadowRoot.getElementById("components");

    this._statsRow = document.createElement("fd-stats-row");
    container.appendChild(this._statsRow);

    this._household = document.createElement("fd-household-section");
    container.appendChild(this._household);

    // The migrated spreadsheet: income, cost ledger, pocket money, transfer
    // choreography and the benchmark comparison. Loads its own data - the plan
    // exists whether or not a bank is linked.
    this._budgetPlan = document.createElement("fd-budget-plan");
    if (this._hass) this._budgetPlan.hass = this._hass;
    container.appendChild(this._budgetPlan);

    this._category = document.createElement("fd-category-section");
    container.appendChild(this._category);

    this._costDist = document.createElement("fd-cost-distribution");
    container.appendChild(this._costDist);

    this._recurring = document.createElement("fd-recurring-list");
    container.appendChild(this._recurring);
    // The plain transaction list moved to the Overview tab (fd-overview).
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

  _bindNav(root, selector) {
    root.querySelector(selector)?.addEventListener("click", (ev) => {
      window._fd.navigate(window._fd.INTEGRATION_PATH, ev);
    });
  }

  _onData(data) {
    const { tSync } = window._fd;

    // Update header timestamp, rate limit, and demo state
    const header = this.shadowRoot.querySelector("fd-header");
    if (header) {
      if (data.lastRefresh !== undefined) header.lastRefresh = data.lastRefresh;
      if (data.rateLimitedUntil !== undefined) header.rateLimitedUntil = data.rateLimitedUntil;
      if (data.lastRefreshStats !== undefined) header.lastRefreshStats = data.lastRefreshStats;
      if (data.demoMode !== undefined) header.demoMode = data.demoMode;
    }

    // Loading state (e.g. during demo toggle)
    if (data.loading) {
      this._showOverlay("loading", tSync("panel.loading"));
      return;
    }

    if (data.error) {
      this._showOverlay("error",
        `<div>${tSync("panel.error")} <a id="errorNavBtn" href="${window._fd.INTEGRATION_PATH}" style="color:var(--ac);text-decoration:underline;">${tSync("panel.error.connect")}</a></div>`);
      this._bindNav(this._overlay, "#errorNavBtn");
      return;
    }

    // While a refresh is in flight and there's no data yet, keep the
    // user on the loading screen instead of flashing the onboarding
    // prompt momentarily.
    if (data.isRefreshing && data.accountCount === 0 && !data.demoMode) {
      this._showOverlay("loading", tSync("panel.loading.refresh"));
      return;
    }

    // Onboarding: no accounts and no demo -> link to the integration page
    if (data.accountCount === 0 && !data.demoMode) {
      const needsRebind = this._overlayState !== "onboarding";
      this._showOverlay("onboarding", `
<div style="text-align:center;padding:60px 20px;max-width:480px;margin:0 auto;">
  <h2 style="margin:0 0 8px;font-size:20px;font-weight:600;">${tSync("panel.onboarding.title")}</h2>
  <p style="color:var(--tx2);margin:0 0 24px;line-height:1.5;">
    ${tSync("panel.onboarding.body")}
  </p>
  <a id="onboardingConnectBtn" href="${window._fd.INTEGRATION_PATH}" style="
    display:inline-block;padding:12px 28px;border-radius:12px;border:none;text-decoration:none;
    background:var(--ac);color:var(--bg);font-size:15px;font-weight:700;
    cursor:pointer;font-family:inherit;margin-bottom:12px;
  ">${tSync("panel.onboarding.cta_link")}</a>
  <div style="margin-top:12px;">
    <button id="onboardingDemoBtn" style="
      padding:10px 24px;border-radius:10px;border:2px solid var(--warning-color,#f39c12);
      background:transparent;color:var(--warning-color,#f39c12);font-size:14px;font-weight:600;
      cursor:pointer;font-family:inherit;
    ">${tSync("panel.onboarding.cta_demo")}</button>
  </div>
</div>`);
      if (needsRebind) {
        // _showOverlay() rebuilds innerHTML so listeners must be re-attached.
        this._bindNav(this._overlay, "#onboardingConnectBtn");
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
  }
}

window._fd.defineOnce("finance-dashboard-panel", FinanceDashboardPanel);
