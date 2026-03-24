/**
 * Finance Dashboard — Sidebar Panel
 *
 * Web Component for the Home Assistant sidebar panel.
 * Displays account balances, transaction overview, and budget summary.
 *
 * SECURITY: Never caches or stores financial data in localStorage/sessionStorage.
 * All data is fetched fresh from the HA API on each load.
 */

class FinanceDashboardPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = {};
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot.querySelector(".fd-container")) {
      this._render();
    }
    this._refreshData();
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          --fd-bg: var(--primary-background-color, #1a1a2e);
          --fd-surface: var(--card-background-color, #16213e);
          --fd-text: var(--primary-text-color, #e0e0e0);
          --fd-text-secondary: var(--secondary-text-color, #a0a0a0);
          --fd-accent: var(--accent-color, #4ecca3);
          --fd-danger: #e74c3c;
          --fd-warning: #f39c12;
          --fd-success: #27ae60;
          --fd-radius: 12px;
          --fd-font: var(--paper-font-body1_-_font-family, 'Segoe UI', sans-serif);

          display: block;
          font-family: var(--fd-font);
          color: var(--fd-text);
          background: var(--fd-bg);
          min-height: 100vh;
          padding: 24px;
          box-sizing: border-box;
        }

        .fd-container {
          max-width: 1200px;
          margin: 0 auto;
        }

        .fd-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 24px;
        }

        .fd-header h1 {
          margin: 0;
          font-size: 28px;
          font-weight: 600;
        }

        .fd-refresh-btn {
          background: var(--fd-surface);
          border: 1px solid rgba(255,255,255,0.1);
          color: var(--fd-text);
          padding: 8px 16px;
          border-radius: var(--fd-radius);
          cursor: pointer;
          font-size: 14px;
          transition: background 0.2s;
        }
        .fd-refresh-btn:hover {
          background: rgba(255,255,255,0.1);
        }

        .fd-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
          gap: 16px;
          margin-bottom: 24px;
        }

        .fd-card {
          background: var(--fd-surface);
          border-radius: var(--fd-radius);
          padding: 20px;
          border: 1px solid rgba(255,255,255,0.05);
        }

        .fd-card h2 {
          margin: 0 0 12px 0;
          font-size: 16px;
          color: var(--fd-text-secondary);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .fd-balance {
          font-size: 32px;
          font-weight: 700;
          color: var(--fd-accent);
        }

        .fd-balance.negative {
          color: var(--fd-danger);
        }

        .fd-account-name {
          font-size: 14px;
          color: var(--fd-text-secondary);
          margin-top: 4px;
        }

        .fd-transactions {
          list-style: none;
          padding: 0;
          margin: 0;
        }

        .fd-transaction {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px 0;
          border-bottom: 1px solid rgba(255,255,255,0.05);
        }

        .fd-transaction:last-child {
          border-bottom: none;
        }

        .fd-txn-info {
          flex: 1;
        }

        .fd-txn-description {
          font-size: 14px;
          margin-bottom: 2px;
        }

        .fd-txn-category {
          font-size: 12px;
          color: var(--fd-text-secondary);
          text-transform: capitalize;
        }

        .fd-txn-amount {
          font-size: 14px;
          font-weight: 600;
          white-space: nowrap;
          margin-left: 12px;
        }

        .fd-txn-amount.positive {
          color: var(--fd-success);
        }
        .fd-txn-amount.negative {
          color: var(--fd-danger);
        }

        .fd-category-bar {
          display: flex;
          height: 8px;
          border-radius: 4px;
          overflow: hidden;
          margin: 8px 0;
          background: rgba(255,255,255,0.05);
        }

        .fd-loading {
          text-align: center;
          padding: 40px;
          color: var(--fd-text-secondary);
        }

        .fd-empty {
          text-align: center;
          padding: 60px 20px;
          color: var(--fd-text-secondary);
        }

        .fd-empty-icon {
          font-size: 48px;
          margin-bottom: 16px;
        }
      </style>

      <div class="fd-container">
        <div class="fd-header">
          <h1>Finance Dashboard</h1>
          <button class="fd-refresh-btn" id="refreshBtn">Refresh</button>
        </div>

        <div id="content" class="fd-loading">
          Loading financial data...
        </div>
      </div>
    `;

    this.shadowRoot
      .getElementById("refreshBtn")
      .addEventListener("click", () => this._refreshData());
  }

  async _refreshData() {
    if (!this._hass) return;

    const content = this.shadowRoot.getElementById("content");
    if (!content) return;

    try {
      const [balances, transactions, summary] = await Promise.all([
        this._fetchApi("/api/finance_dashboard/balances"),
        this._fetchApi("/api/finance_dashboard/transactions"),
        this._fetchApi("/api/finance_dashboard/summary"),
      ]);

      this._renderDashboard(content, balances, transactions, summary);
    } catch (err) {
      content.innerHTML = `
        <div class="fd-empty">
          <div class="fd-empty-icon">&#128170;</div>
          <p>Connect your bank account to get started.</p>
          <p style="font-size: 12px">
            Go to Settings &rarr; Integrations &rarr; Finance Dashboard
          </p>
        </div>
      `;
    }
  }

  _renderDashboard(container, balances, transactions, summary) {
    let balanceCards = "";
    if (balances && typeof balances === "object") {
      for (const [id, account] of Object.entries(balances)) {
        const balance = account.balances?.[0]?.balanceAmount?.amount || "0.00";
        const currency = account.balances?.[0]?.balanceAmount?.currency || "EUR";
        const isNeg = parseFloat(balance) < 0;
        balanceCards += `
          <div class="fd-card">
            <h2>Balance</h2>
            <div class="fd-balance ${isNeg ? "negative" : ""}">
              ${this._formatCurrency(balance, currency)}
            </div>
            <div class="fd-account-name">
              ${account.account_name} (${account.iban_masked})
            </div>
          </div>
        `;
      }
    }

    let summaryCard = "";
    if (summary && summary.total_income !== undefined) {
      summaryCard = `
        <div class="fd-card">
          <h2>Monthly Summary</h2>
          <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
            <span>Income</span>
            <span class="fd-txn-amount positive">
              ${this._formatCurrency(summary.total_income, "EUR")}
            </span>
          </div>
          <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
            <span>Expenses</span>
            <span class="fd-txn-amount negative">
              -${this._formatCurrency(summary.total_expenses, "EUR")}
            </span>
          </div>
          <hr style="border-color: rgba(255,255,255,0.1); margin: 12px 0;">
          <div style="display: flex; justify-content: space-between;">
            <span style="font-weight: 600;">Balance</span>
            <span class="fd-balance" style="font-size: 24px;">
              ${this._formatCurrency(summary.balance, "EUR")}
            </span>
          </div>
        </div>
      `;
    }

    let transactionsList = "";
    const txns = transactions?.transactions || [];
    if (txns.length > 0) {
      const items = txns
        .slice(0, 20)
        .map((txn) => {
          const amount = parseFloat(txn.amount);
          const isPositive = amount >= 0;
          return `
          <li class="fd-transaction">
            <div class="fd-txn-info">
              <div class="fd-txn-description">
                ${txn.creditor || txn.description || "Unknown"}
              </div>
              <div class="fd-txn-category">${txn.category} &middot; ${txn.date}</div>
            </div>
            <div class="fd-txn-amount ${isPositive ? "positive" : "negative"}">
              ${isPositive ? "+" : ""}${this._formatCurrency(txn.amount, txn.currency)}
            </div>
          </li>
        `;
        })
        .join("");

      transactionsList = `
        <div class="fd-card" style="grid-column: 1 / -1;">
          <h2>Recent Transactions</h2>
          <ul class="fd-transactions">${items}</ul>
        </div>
      `;
    }

    container.innerHTML = `
      <div class="fd-grid">
        ${balanceCards}
        ${summaryCard}
      </div>
      ${transactionsList}
    `;
    container.classList.remove("fd-loading");
  }

  _formatCurrency(amount, currency) {
    const num = parseFloat(amount);
    return new Intl.NumberFormat("de-DE", {
      style: "currency",
      currency: currency || "EUR",
    }).format(num);
  }

  async _fetchApi(path) {
    const resp = await this._hass.callApi("GET", path.replace("/api/", ""));
    return resp;
  }
}

customElements.define("finance-dashboard-panel", FinanceDashboardPanel);
