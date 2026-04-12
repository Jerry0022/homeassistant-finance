/**
 * fd-data-provider — Invisible component that bridges HA entities to dashboard UI.
 *
 * Reads balance/summary data from HA sensor entities and supplements with
 * one API call for household + recurring data. Dispatches a single
 * "fd-data-updated" CustomEvent whenever data changes.
 *
 * Entity discovery uses the HA Entity Registry (platform = "finance_dashboard")
 * to reliably find our entities regardless of their generated entity_id.
 */

const DEBOUNCE_MS = 200;
const DOMAIN = "finance_dashboard";

class FdDataProvider extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._data = null;
    this._debounceTimer = null;
    this._prevStateHash = "";
    this._initialRebuildDone = false;
    this._loading = false;
    this._demoMode = false;
    this._demoToggling = false;
    // Entity registry map: entity_id → unique_id (for our platform only)
    this._entityMap = null;
    this._registryLoading = false;
  }

  get data() {
    return this._data;
  }

  get demoMode() {
    return this._demoMode;
  }

  set hass(hass) {
    this._hass = hass;
    // Load entity registry on first hass assignment
    if (!this._entityMap && !this._registryLoading) {
      this._loadEntityRegistry();
    }
    // In demo mode, don't watch entity changes
    if (this._demoMode) return;
    // Debounce: hass changes many times per second
    clearTimeout(this._debounceTimer);
    this._debounceTimer = setTimeout(() => this._onHassChanged(), DEBOUNCE_MS);
  }

  /** Load entity registry and build lookup map for our integration. */
  async _loadEntityRegistry() {
    if (!this._hass || !this._hass.connection) return;
    this._registryLoading = true;
    try {
      const registry = await this._hass.connection.sendMessagePromise({
        type: "config/entity_registry/list",
      });
      this._entityMap = new Map();
      for (const entry of registry) {
        if (entry.platform === DOMAIN) {
          this._entityMap.set(entry.entity_id, entry.unique_id);
        }
      }
      // Trigger initial rebuild now that we know our entities
      this._prevStateHash = "";
      this._initialRebuildDone = false;
      this._onHassChanged();
    } catch (e) {
      console.error("fd-data-provider: entity registry load failed:", e);
      this._entityMap = new Map();
    } finally {
      this._registryLoading = false;
    }
  }

  /** Refresh entity registry (e.g. after setup wizard completes). */
  async refreshRegistry() {
    this._entityMap = null;
    this._registryLoading = false;
    await this._loadEntityRegistry();
  }

  /** Toggle demo mode — fetches demo data from API. Guarded against rapid clicks. */
  async toggleDemo() {
    if (!this._hass || this._demoToggling) return this._demoMode;
    this._demoToggling = true;
    try {
      const result = await this._hass.callApi("POST", `${DOMAIN}/demo/toggle`);
      this._demoMode = result.demo_mode;
      if (this._demoMode) {
        await this._loadDemoData();
      } else {
        // Revert to entity-based data
        this._prevStateHash = "";
        await this._rebuild();
      }
      return this._demoMode;
    } catch (e) {
      console.error("fd-data-provider: demo toggle failed:", e);
      return this._demoMode;
    } finally {
      this._demoToggling = false;
    }
  }

  /** Load demo data from the API endpoint. */
  async _loadDemoData() {
    if (!this._hass) return;
    // Dispatch loading state
    this.dispatchEvent(new CustomEvent("fd-data-updated", {
      detail: { loading: true, demoMode: true },
      bubbles: true,
      composed: true,
    }));
    try {
      const data = await this._hass.callApi("GET", `${DOMAIN}/demo/data`);
      this._data = data;
      this.dispatchEvent(new CustomEvent("fd-data-updated", {
        detail: { ...data, demoMode: true },
        bubbles: true,
        composed: true,
      }));
    } catch (e) {
      console.error("fd-data-provider: demo data fetch failed:", e);
      this.dispatchEvent(new CustomEvent("fd-data-updated", {
        detail: { error: "Demo-Daten konnten nicht geladen werden", demoMode: true },
        bubbles: true,
        composed: true,
      }));
    }
  }

  /** Trigger a full data rebuild (manual refresh). */
  async refresh() {
    if (!this._hass) return;
    if (this._demoMode) {
      // In demo mode, just regenerate demo data
      await this._loadDemoData();
      return;
    }
    // Ask HA to refresh transactions, which triggers coordinator update
    try {
      await this._hass.callService(DOMAIN, "refresh_transactions");
    } catch (e) {
      console.warn("fd-data-provider: refresh_transactions failed:", e);
    }
    // Force immediate rebuild — allow API fallback for household/recurring
    this._prevStateHash = "";
    await this._rebuild(true);
  }

  /** Check if relevant entity states changed and rebuild if needed. */
  _onHassChanged() {
    if (!this._hass || !this._entityMap) return;
    const hash = this._computeStateHash();
    // First call must always trigger rebuild (even with empty hash)
    if (this._initialRebuildDone && hash === this._prevStateHash) return;
    this._initialRebuildDone = true;
    this._prevStateHash = hash;
    this._rebuild();
  }

  /** Quick hash of relevant entity states to detect changes. */
  _computeStateHash() {
    if (!this._hass || !this._hass.states || !this._entityMap) return "";
    const parts = [];
    for (const entityId of this._entityMap.keys()) {
      const state = this._hass.states[entityId];
      if (state) {
        parts.push(`${entityId}=${state.state}|${state.last_updated}`);
      }
    }
    return parts.join(";");
  }

  /**
   * Rebuild the unified data object from entities.
   * @param {boolean} allowApiFallback — if true, fetch household/recurring
   *   from the summary API when not available in entity attributes.
   *   Only true during explicit user-triggered refresh.
   */
  async _rebuild(allowApiFallback = false) {
    if (!this._hass || this._loading) return;
    this._loading = true;

    try {
      const data = {
        accounts: [],
        totalBalance: 0,
        accountCount: 0,
        summary: {
          totalIncome: 0,
          totalExpenses: 0,
          balance: 0,
          categories: {},
          transactionCount: 0,
          fixedCosts: 0,
          variableCosts: 0,
          month: new Date().getMonth() + 1,
          year: new Date().getFullYear(),
        },
        budgets: {},
        splitModel: "proportional",
        household: null,
        recurring: [],
        loading: false,
        error: null,
        lastRefresh: null,
        rateLimitedUntil: null,
      };

      // 1. Read entities using registry-based lookup
      let totalEntityId = null;
      let summaryEntityId = null;

      for (const [entityId, uniqueId] of this._entityMap.entries()) {
        const state = this._hass.states[entityId];
        if (!state) continue;

        // Account balance sensors: unique_id = finance_dashboard_{id}_balance
        // (excludes total_balance and monthly_summary)
        if (uniqueId === `${DOMAIN}_total_balance`) {
          totalEntityId = entityId;
          continue;
        }
        if (uniqueId === `${DOMAIN}_monthly_summary`) {
          summaryEntityId = entityId;
          continue;
        }
        if (uniqueId.startsWith(`${DOMAIN}_`) && uniqueId.endsWith("_balance")) {
          const val = parseFloat(state.state);
          if (isNaN(val)) continue;
          const attrs = state.attributes || {};
          data.accounts.push({
            entityId,
            name: attrs.custom_name || attrs.friendly_name || entityId,
            institution: attrs.institution || "",
            balance: val,
            ibanMasked: attrs.iban_masked || "****",
            currency: attrs.unit_of_measurement || "EUR",
            person: attrs.person || "",
          });
          data.totalBalance += val;
          data.accountCount++;
          continue;
        }

        // Budget numbers: unique_id = finance_dashboard_budget_{category}
        if (uniqueId.startsWith(`${DOMAIN}_budget_`)) {
          const cat = uniqueId.replace(`${DOMAIN}_budget_`, "");
          const val = parseFloat(state.state);
          if (!isNaN(val) && val > 0) {
            data.budgets[cat] = val;
          }
          continue;
        }

        // Split model: unique_id = finance_dashboard_split_model
        if (uniqueId === `${DOMAIN}_split_model`) {
          data.splitModel = state.state || "proportional";
          continue;
        }
      }

      // 2. Read total balance sensor (may differ from sum due to rounding)
      if (totalEntityId) {
        const totalEntity = this._hass.states[totalEntityId];
        if (totalEntity && !isNaN(parseFloat(totalEntity.state))) {
          data.totalBalance = parseFloat(totalEntity.state);
        }
      }

      // 3. Read monthly summary sensor
      if (summaryEntityId) {
        const summaryEntity = this._hass.states[summaryEntityId];
        if (summaryEntity) {
          const sa = summaryEntity.attributes || {};
          data.summary.totalIncome = sa.total_income || 0;
          data.summary.totalExpenses = sa.total_expenses || 0;
          data.summary.balance = parseFloat(summaryEntity.state) || 0;
          data.summary.categories = sa.categories || {};
          data.summary.transactionCount = sa.transaction_count || 0;
          data.summary.fixedCosts = sa.fixed_costs || 0;
          data.summary.variableCosts = sa.variable_costs || 0;
          data.summary.month = sa.month || data.summary.month;
          data.summary.year = sa.year || data.summary.year;
          data.lastRefresh = sa.last_refresh || null;
          data.rateLimitedUntil = sa.rate_limited_until || null;

          // Household and recurring from entity attrs (added in v0.7.9+)
          if (sa.household) data.household = sa.household;
          if (sa.recurring) data.recurring = sa.recurring;
        }
      }

      // 4. Fetch household/recurring from API ONLY on explicit user refresh
      if (allowApiFallback &&
          (!data.household || !data.recurring || data.recurring.length === 0)) {
        try {
          const summary = await this._hass.callApi("GET", `${DOMAIN}/summary`);
          if (summary) {
            if (!data.household && summary.household) {
              data.household = summary.household;
            }
            if ((!data.recurring || data.recurring.length === 0) && summary.recurring) {
              data.recurring = summary.recurring;
            }
          }
        } catch (e) {
          console.warn("fd-data-provider: API fallback for household/recurring failed:", e);
        }
      }

      this._data = data;
      data.demoMode = this._demoMode;
      this.dispatchEvent(new CustomEvent("fd-data-updated", {
        detail: data,
        bubbles: true,
        composed: true,
      }));
    } catch (e) {
      console.error("fd-data-provider: rebuild failed:", e);
      if (this._data) {
        this._data.error = e.message;
      }
    } finally {
      this._loading = false;
    }
  }
}

customElements.define("fd-data-provider", FdDataProvider);
