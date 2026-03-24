/**
 * Finance Dashboard — Lovelace Card
 *
 * A compact Lovelace card showing account balance and recent transactions.
 * Can be added to any HA dashboard via the card picker.
 *
 * Usage:
 *   type: custom:finance-dashboard-card
 *   show_transactions: true
 *   max_transactions: 5
 */

class FinanceDashboardCard extends HTMLElement {
  set hass(hass) {
    if (!this.content) {
      this.innerHTML = `
        <ha-card header="Finance Dashboard">
          <div class="card-content" id="fd-card-content">
            <p style="color: var(--secondary-text-color);">Loading...</p>
          </div>
        </ha-card>
      `;
      this.content = this.querySelector("#fd-card-content");
    }

    // Data refresh is handled by the panel API
    // Card provides a compact overview widget
    this._hass = hass;
    this._updateCard();
  }

  setConfig(config) {
    this._config = config;
    this._showTransactions = config.show_transactions !== false;
    this._maxTransactions = config.max_transactions || 5;
  }

  async _updateCard() {
    if (!this._hass || !this.content) return;

    try {
      const balances = await this._hass.callApi(
        "GET",
        "finance_dashboard/balances"
      );

      let html = "";
      for (const [id, account] of Object.entries(balances)) {
        const balance =
          account.balances?.[0]?.balanceAmount?.amount || "0.00";
        const currency =
          account.balances?.[0]?.balanceAmount?.currency || "EUR";
        const formatted = new Intl.NumberFormat("de-DE", {
          style: "currency",
          currency,
        }).format(parseFloat(balance));

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

      this.content.innerHTML = html || "<p>No accounts linked.</p>";
    } catch {
      this.content.innerHTML =
        '<p style="color: var(--secondary-text-color);">Setup required.</p>';
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
              Show Transactions
            </label>
            <ha-switch id="fd-show-txn"></ha-switch>
          </div>
          <div>
            <label style="display: block; margin-bottom: 4px; font-weight: 500;">
              Max Transactions
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
  name: "Finance Dashboard",
  description: "Display banking balances and recent transactions.",
});
