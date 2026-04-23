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
    this._pendingRebuild = false;
    this._demoMode = false;
    this._demoToggling = false;
    // Entity registry map: entity_id → unique_id (for our platform only)
    this._entityMap = null;
    this._registryLoading = false;
    // Unsubscribe handle for entity_registry_updated subscription
    this._registryUnsub = null;
    // Cached admin-only transaction list (from /transactions, cache-read).
    // Kept across rebuilds so entity-only state changes don't trigger new
    // fetches. Refreshed on first rebuild with accounts and on every
    // user-triggered refresh().
    this._cachedTransactions = [];
  }

  disconnectedCallback() {
    if (this._registryUnsub) {
      try { this._registryUnsub(); } catch (e) { /* ignore */ }
      this._registryUnsub = null;
    }
    clearTimeout(this._debounceTimer);
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
      // Subscribe to registry changes so newly created entities (e.g.
      // after setup wizard completion) are picked up automatically
      // without depending on a fixed timer in the panel shell.
      await this._subscribeRegistryUpdates();
    } catch (e) {
      console.error("fd-data-provider: entity registry load failed:", e);
      this._entityMap = new Map();
    } finally {
      this._registryLoading = false;
    }
  }

  /** Subscribe to entity_registry_updated events for our platform. */
  async _subscribeRegistryUpdates() {
    if (this._registryUnsub || !this._hass || !this._hass.connection) return;
    try {
      this._registryUnsub = await this._hass.connection.subscribeEvents(
        () => {
          // Cheap reload — registry list calls are tiny
          this._reloadRegistryFromEvent();
        },
        "entity_registry_updated",
      );
    } catch (e) {
      console.warn("fd-data-provider: registry event subscribe failed:", e);
    }
  }

  /** Re-fetch registry on update event (debounced via micro-task). */
  async _reloadRegistryFromEvent() {
    if (!this._hass || !this._hass.connection) return;
    try {
      const registry = await this._hass.connection.sendMessagePromise({
        type: "config/entity_registry/list",
      });
      const next = new Map();
      for (const entry of registry) {
        if (entry.platform === DOMAIN) {
          next.set(entry.entity_id, entry.unique_id);
        }
      }
      // Only rebuild if the entity set actually changed
      const changed =
        !this._entityMap ||
        next.size !== this._entityMap.size ||
        [...next.keys()].some((k) => !this._entityMap.has(k));
      this._entityMap = next;
      if (changed) {
        this._prevStateHash = "";
        this._onHassChanged();
      }
    } catch (e) {
      console.warn("fd-data-provider: registry reload failed:", e);
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

  /** Trigger a full data rebuild (manual refresh).
   *
   *  Returns a stats object the panel can surface in a toast:
   *    { outcome, accounts, transactions, new, duration_ms, errors,
   *      rate_limited_until, last_refresh, cache_age_seconds }
   *
   *  "outcome" is one of: ok | partial | rate_limited | error | demo.
   */
  async refresh() {
    if (!this._hass) return { outcome: "error", errors: ["no hass"] };
    if (this._demoMode) {
      await this._loadDemoData();
      return { outcome: "demo" };
    }
    // Notify listeners that a live fetch started — used by the header
    // to show the spinner chip instead of the static timestamp.
    this.dispatchEvent(new CustomEvent("fd-refresh-started", {
      bubbles: true,
      composed: true,
    }));

    let resultStatus = null;
    // Capture the current state hash so we can detect when coordinator
    // has pushed fresh entity state after the refresh completes.
    const preRefreshHash = this._computeStateHash();

    try {
      // Dedicated endpoint blocks until the refresh completes and
      // returns structured stats. Using this instead of the HA service
      // call avoids the pre-2024 no-response behaviour on older cores.
      const resp = await this._hass.callApi("POST", `${DOMAIN}/refresh`);
      resultStatus = resp?.status || null;
      if (resp && resp.ok === false) {
        // Rate-limited or hard error — still dispatch the status so the
        // header can render the "Morgen verfügbar" chip correctly.
        this.dispatchEvent(new CustomEvent("fd-refresh-done", {
          detail: {
            status: resultStatus,
            ok: false,
            reason: resp.reason,
          },
          bubbles: true,
          composed: true,
        }));
      }
    } catch (e) {
      console.warn("fd-data-provider: /refresh endpoint failed:", e);
    }

    // Do NOT call _rebuild() immediately — the HA coordinator pushes entity
    // state via WebSocket asynchronously, so hass.states may still be stale.
    // Instead, reset the hash so the next set hass() tick triggers a rebuild
    // with the fresh states. Also set _pendingRebuild so that if a rebuild
    // is currently in flight it will re-run once it finishes.
    this._prevStateHash = "";
    this._pendingRebuild = false; // clear any stale pending flag

    // Poll for fresh states for up to 5 s (max ~10 ticks, 500 ms apart).
    // As soon as the state hash changes (coordinator pushed new values) OR
    // we time out, trigger one authoritative rebuild with API fallback.
    // This terminates unconditionally — no infinite loops.
    const POLL_INTERVAL = 500;
    const POLL_MAX = 10;
    let pollCount = 0;
    await new Promise((resolve) => {
      const poll = () => {
        pollCount++;
        const currentHash = this._computeStateHash();
        if (currentHash !== preRefreshHash || pollCount >= POLL_MAX) {
          resolve();
        } else {
          setTimeout(poll, POLL_INTERVAL);
        }
      };
      // First tick after a short delay so the WS push can arrive
      setTimeout(poll, POLL_INTERVAL);
    });

    await this._rebuild(true);

    if (resultStatus && resultStatus.stats) {
      this.dispatchEvent(new CustomEvent("fd-refresh-done", {
        detail: {
          status: resultStatus,
          ok: resultStatus.stats.outcome === "ok",
          reason: resultStatus.stats.outcome,
        },
        bubbles: true,
        composed: true,
      }));
    }
    return resultStatus || {};
  }

  /** Fetch cached transactions (admin-only, cache-read, unbounded-safe). */
  async _fetchTransactions() {
    if (!this._hass) return;
    try {
      const resp = await this._hass.callApi("GET", `${DOMAIN}/transactions`);
      if (resp && resp.privacy === "admin_full"
          && Array.isArray(resp.transactions)) {
        this._cachedTransactions = resp.transactions;
      } else {
        // Non-admin or empty response → no detail view available
        this._cachedTransactions = [];
      }
    } catch (e) {
      console.warn("fd-data-provider: /transactions fetch failed:", e);
    }
  }

  /** Fetch the current refresh status (cache-only, unbounded-safe). */
  async fetchRefreshStatus() {
    if (!this._hass) return null;
    try {
      return await this._hass.callApi("GET", `${DOMAIN}/refresh_status`);
    } catch (e) {
      console.warn("fd-data-provider: /refresh_status failed:", e);
      return null;
    }
  }

  /** Check if relevant entity states changed and rebuild if needed. */
  _onHassChanged() {
    if (!this._hass || !this._entityMap) return;
    const hash = this._computeStateHash();
    // First call must always trigger rebuild (even with empty hash)
    if (this._initialRebuildDone && hash === this._prevStateHash) return;
    this._initialRebuildDone = true;
    // Only advance the hash AFTER rebuild completes — if _rebuild() bails
    // early due to _loading=true (race with a concurrent rebuild), do NOT
    // update _prevStateHash so the next hass tick will retry.
    if (this._loading) {
      // A rebuild is already in flight; schedule a retry after it finishes.
      // _pendingRebuild is cleared inside _rebuild() in the finally block.
      this._pendingRebuild = true;
      return;
    }
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
        lastRefreshStats: null,
        isRefreshing: false,
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
          data.lastRefreshStats = sa.last_refresh_stats || null;
          data.isRefreshing = !!sa.is_refreshing;

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

      // 5. Transaction log (cache-read endpoint, unbounded-safe). Fetch on
      // first rebuild with linked accounts and on every user-triggered
      // refresh. Skip entirely in demo mode — demo data has no real txns.
      if (!this._demoMode && data.accountCount > 0) {
        if (allowApiFallback || this._cachedTransactions.length === 0) {
          await this._fetchTransactions();
        }
      } else if (this._demoMode) {
        this._cachedTransactions = [];
      }
      data.transactions = this._cachedTransactions;

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
      // If a hass-change arrived while we were loading, run a fresh rebuild
      // now that the lock is released. This prevents the race where
      // _onHassChanged saw _loading=true and skipped updating _prevStateHash,
      // leaving the panel stuck on stale (empty) data after a refresh.
      if (this._pendingRebuild) {
        this._pendingRebuild = false;
        // Re-enter _onHassChanged so hash comparison runs cleanly
        this._onHassChanged();
      }
    }
  }
}

customElements.define("fd-data-provider", FdDataProvider);
