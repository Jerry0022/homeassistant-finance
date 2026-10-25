/**
 * Finance — Lovelace Card
 *
 * A compact Lovelace card with the facts: total balance, accounts and a
 * warning chip when a bank needs attention (consent, block, last error).
 * Can be added to any HA dashboard via the card picker.
 *
 * Update strategy:
 *  - Fetch data once when the card is first rendered
 *  - Re-fetch at most every 10 minutes, never on every hass setter call
 *    (hass setter fires on every HA state change — fetching there causes
 *     API rate-limit exhaustion within minutes)
 *
 * Delivery: loaded by finance-dashboard-kit.js, which the integration adds to
 * every dashboard automatically (no Lovelace resource needed).
 *
 * Usage:
 *   type: custom:finance-dashboard-card
 *   show_transactions: true
 *   max_transactions: 5
 */

const CARD_REFRESH_INTERVAL_MS = 10 * 60 * 1000; // 10 minutes

class FinanceDashboardCard extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._lastFetch = 0;
    this._fetching = false;
    this._config = {};
  }

  set hass(hass) {
    if (!this.content) {
      this.innerHTML = `
        <ha-card header="Finance">
          <div class="card-content" id="fd-card-content">
            <p style="color: var(--secondary-text-color);">&#8230;</p>
          </div>
        </ha-card>
      `;
      this.content = this.querySelector("#fd-card-content");
    }

    this._hass = hass;
    if (window._fd) window._fd._hass = hass;

    // Throttle: only fetch if 10 minutes have passed since the last fetch
    const now = Date.now();
    if (now - this._lastFetch >= CARD_REFRESH_INTERVAL_MS) {
      this._updateCard();
    }
  }

  setConfig(config) {
    this._config = config;
    this._showTransactions = config.show_transactions !== false;
    this._maxTransactions = config.max_transactions || 5;
  }

  async _updateCard() {
    if (!this._hass || !this.content || this._fetching) return;
    this._fetching = true;
    this._lastFetch = Date.now();
    const esc = (v) => (window._fd ? window._fd.escHtml(v) : String(v ?? ""));
    const tr = (k, vars) => (window._fd ? window._fd.tSync(k, vars) : k);

    try {
      if (window._fd) await window._fd.t("card.title"); // load the user's locale
      // Both are cache reads - the card never triggers a live bank call.
      const [balances, status] = await Promise.all([
        this._hass.callApi("GET", "finance_dashboard/balances"),
        this._hass.callApi("GET", "finance_dashboard/bank_status").catch(() => null),
      ]);

      const fmt = (amount, currency) =>
        new Intl.NumberFormat("de-DE", { style: "currency", currency: currency || "EUR" })
          .format(parseFloat(amount));

      const accounts = Object.values(balances || {}).filter((a) => a && !a.error);
      let total = 0;
      let rows = "";
      for (const account of accounts) {
        // Prefer the booked balance, fall back to the first reported entry.
        const raw = account.balances || [];
        const chosen = account.booked
          ? { balanceAmount: account.booked }
          : raw.find((b) => ["closingBooked", "interimAvailable", "interimBooked"].includes(b.balanceType)) || raw[0];
        const amount = parseFloat(chosen?.balanceAmount?.amount ?? "0") || 0;
        total += amount;
        rows += `
          <div style="display:flex;justify-content:space-between;gap:12px;margin-bottom:6px;">
            <div style="font-size:13px;min-width:0;overflow-wrap:anywhere;">
              ${esc(account.account_name)}
              <span style="color:var(--secondary-text-color);font-size:12px;">${esc(account.iban_masked)}</span>
            </div>
            <div style="font-weight:600;white-space:nowrap;">${fmt(amount, chosen?.balanceAmount?.currency)}</div>
          </div>`;
      }

      // Warning chip: worst bank state wins (expired > expiring > blocked > error).
      let warn = "";
      const banks = (status && status.banks) || [];
      const now = Date.now();
      const key = banks.some((b) => b.consent_state === "expired") ? "card.warn_expired"
        : banks.some((b) => b.consent_state === "expiring") ? "card.warn_expiring"
        : banks.some((b) => b.blocked_until && new Date(b.blocked_until).getTime() > now) ? "card.warn_blocked"
        : banks.some((b) => b.last_error) ? "card.warn_error"
        : null;
      if (key) {
        const path = window._fd ? window._fd.INTEGRATION_PATH : "/config/integrations/integration/finance_dashboard";
        warn = `<a href="${path}" data-fd-nav style="display:inline-block;margin-top:8px;padding:3px 10px;border-radius:999px;
          border:1px solid var(--warning-color,#f39c12);color:var(--warning-color,#f39c12);font-size:12px;text-decoration:none;">${esc(tr(key))}</a>`;
      }

      if (!accounts.length) {
        this.content.innerHTML = `<p>${esc(tr("card.empty"))}</p>${warn}`;
      } else {
        const count = accounts.length === 1 ? tr("card.account_one") : tr("card.accounts", { n: accounts.length });
        this.content.innerHTML = `
          <div style="font-size:12px;color:var(--secondary-text-color);">${esc(tr("card.total"))} · ${esc(count)}</div>
          <div style="font-size:28px;font-weight:700;color:var(--accent-color);margin-bottom:10px;">${fmt(total, "EUR")}</div>
          ${rows}${warn}`;
      }
      const link = this.content.querySelector("[data-fd-nav]");
      if (link && window._fd) link.addEventListener("click", (ev) => window._fd.navigate(link.getAttribute("href"), ev));
    } catch {
      this.content.innerHTML =
        `<p style="color: var(--secondary-text-color);">${esc(tr("card.setup"))}</p>`;
    } finally {
      this._fetching = false;
    }
  }

  static getConfigElement() {
    return document.createElement("finance-dashboard-card-editor");
  }

  static getStubConfig() {
    return {
      show_transactions: true,
      max_transactions: 5,
    };
  }

  getCardSize() {
    return 3;
  }

  // Sections view: width in columns (multiple of 3 of the 12-col grid), height in rows.
  getGridOptions() {
    return { columns: 6, min_columns: 3, rows: 3, min_rows: 2, max_rows: 10 };
  }
}

class FinanceDashboardCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = Object.assign({}, config);
    this._render();
  }

  _render() {
    if (!this.innerHTML) {
      this.innerHTML = `
        <div style="padding: 16px;">
          <div style="margin-bottom: 12px;">
            <label style="display: block; margin-bottom: 4px; font-weight: 500;">
              Transaktionen anzeigen
            </label>
            <ha-switch id="fd-show-txn"></ha-switch>
          </div>
          <div>
            <label style="display: block; margin-bottom: 4px; font-weight: 500;">
              Max. Transaktionen
            </label>
            <ha-textfield id="fd-max-txn" type="number" min="1" max="50"
              style="width: 100%;"></ha-textfield>
          </div>
        </div>
      `;
      this.querySelector("#fd-show-txn").addEventListener("change", (e) => {
        this._config.show_transactions = e.target.checked;
        this._dispatch();
      });
      this.querySelector("#fd-max-txn").addEventListener("change", (e) => {
        this._config.max_transactions = parseInt(e.target.value) || 5;
        this._dispatch();
      });
    }

    const toggle = this.querySelector("#fd-show-txn");
    const input = this.querySelector("#fd-max-txn");
    if (toggle) toggle.checked = this._config.show_transactions !== false;
    if (input) input.value = this._config.max_transactions || 5;
  }

  _dispatch() {
    this.dispatchEvent(
      new CustomEvent("config-changed", { detail: { config: this._config } })
    );
  }
}

window._fd.defineOnce("finance-dashboard-card-editor", FinanceDashboardCardEditor);
window._fd.defineOnce("finance-dashboard-card", FinanceDashboardCard);

window._fd.registerCard({
  type: "finance-dashboard-card",
  name: "Finance",
  description: "Kontostand und Transaktionen auf einen Blick.",
});
