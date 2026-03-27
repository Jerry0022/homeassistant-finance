/**
 * Finance — Lovelace Card
 *
 * A compact Lovelace card showing account balances.
 * Can be added to any HA dashboard via the card picker.
 *
 * Update strategy:
 *  - Fetch data once when the card is first rendered
 *  - Re-fetch at most every 10 minutes, never on every hass setter call
 *    (hass setter fires on every HA state change — fetching there causes
 *     API rate-limit exhaustion within minutes)
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
            <p style="color: var(--secondary-text-color);">Lade&#8230;</p>
          </div>
        </ha-card>
      `;
      this.content = this.querySelector("#fd-card-content");
    }

    this._hass = hass;

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

    try {
      const balances = await this._hass.callApi(
        "GET",
        "finance_dashboard/balances"
      );

      let html = "";
      for (const [, account] of Object.entries(balances)) {
        // Prefer closingBooked balance, fall back to first entry
        const raw = account.balances || [];
        const preferred = ["closingBooked", "interimAvailable", "interimBooked"];
        let chosen = raw.find((b) => preferred.includes(b.balanceType)) || raw[0];
        const amount = chosen?.balanceAmount?.amount || "0.00";
        const currency = chosen?.balanceAmount?.currency || "EUR";
        const formatted = new Intl.NumberFormat("de-DE", {
          style: "currency",
          currency,
        }).format(parseFloat(amount));

        html += `
          <div style="margin-bottom: 12px;">
            <div style="font-size: 24px; font-weight: 700; color: var(--accent-color);">
              ${formatted}
            </div>
            <div style="font-size: 12px; color: var(--secondary-text-color);">
              ${account.account_name} (${account.iban_masked})
            </div>
          </div>
        `;
      }

      this.content.innerHTML = html || "<p>Kein Konto verknüpft.</p>";
    } catch {
      this.content.innerHTML =
        '<p style="color: var(--secondary-text-color);">Einrichtung erforderlich.</p>';
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

customElements.define("finance-dashboard-card-editor", FinanceDashboardCardEditor);
customElements.define("finance-dashboard-card", FinanceDashboardCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "finance-dashboard-card",
  name: "Finance",
  description: "Kontostand und Transaktionen auf einen Blick.",
});
