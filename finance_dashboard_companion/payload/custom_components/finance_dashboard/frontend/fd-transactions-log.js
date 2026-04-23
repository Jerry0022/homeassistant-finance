/**
 * fd-transactions-log — Log of imported (cached) transactions.
 *
 * Properties:
 *   data {object} — Unified data object from fd-data-provider
 *
 * Reads data.transactions (admin-only, cache-only). Shows up to 25 rows
 * by default with an expand toggle to reveal the full cached window
 * (up to 100 items returned by /api/finance_dashboard/transactions).
 */

const TX_CAT_LABELS = {
  housing: "Wohnen", loans: "Kredite", food: "Lebensmittel", utilities: "Nebenkosten",
  insurance: "Versicherung", subscriptions: "Abos", transport: "Mobilit\u00e4t",
  cleaning: "Reinigung", income: "Einkommen", transfers: "\u00dcbertr\u00e4ge", other: "Sonstiges",
};

const DEFAULT_LIMIT = 25;

class FdTransactionsLog extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._expanded = false;
  }

  set data(v) { this._data = v; this._render(); }

  _render() {
    const d = this._data;
    const txs = Array.isArray(d?.transactions) ? d.transactions : null;

    // Gate: only render if at least one account is linked AND data was
    // refreshed at least once (lastRefresh is set). Matches the user's
    // request to reveal the log only after a first successful refresh.
    const hasAccounts = (d?.accountCount || 0) > 0 || d?.demoMode;
    const everRefreshed = !!d?.lastRefresh || d?.demoMode;
    if (!hasAccounts || !everRefreshed) {
      this.shadowRoot.innerHTML = "";
      return;
    }

    if (!txs) {
      // Data provider is still loading — keep the section hidden rather
      // than flashing an empty state.
      this.shadowRoot.innerHTML = "";
      return;
    }

    const total = txs.length;
    const limit = this._expanded ? total : DEFAULT_LIMIT;
    const visible = txs.slice(0, limit);

    const eur = (v) => new Intl.NumberFormat("de-DE", {
      style: "currency", currency: "EUR",
    }).format(Number(v) || 0);

    const rows = visible.map((t) => {
      const amount = parseFloat(t.amount);
      const isPositive = !isNaN(amount) && amount > 0;
      const amountClass = isPositive ? "pos" : "neg";
      const sign = isPositive ? "+" : "";
      const label = t.creditor || t.description || "\u2014";
      const sub = t.creditor && t.description && t.creditor !== t.description
        ? t.description : "";
      const cat = TX_CAT_LABELS[t.category] || t.category || "Sonstiges";
      const dateStr = this._formatDate(t.date);
      const pending = t.status === "pending"
        ? `<span class="tx-pending" title="Vorgemerkt (noch nicht gebucht)">vorgemerkt</span>`
        : "";
      const account = t.account_name
        ? `<span class="tx-acc">${this._esc(t.account_name)}</span>`
        : "";

      return `<div class="tx-item">
        <div class="tx-date">${this._esc(dateStr)}</div>
        <div class="tx-main">
          <div class="tx-label">${this._esc(label)} ${pending}</div>
          ${sub ? `<div class="tx-sub">${this._esc(sub)}</div>` : ""}
          <div class="tx-meta">
            <span class="tx-cat">${this._esc(cat)}</span>
            ${account}
          </div>
        </div>
        <div class="tx-amount ${amountClass}">${sign}${eur(amount)}</div>
      </div>`;
    }).join("");

    const toggleBtn = total > DEFAULT_LIMIT
      ? `<button class="tx-toggle" id="toggleBtn">
          ${this._expanded ? "Weniger anzeigen" : `Alle ${total} anzeigen`}
        </button>`
      : "";

    const emptyState = total === 0
      ? `<div class="tx-empty">Noch keine Transaktionen im Cache. Nach der n\u00e4chsten Aktualisierung erscheinen sie hier.</div>`
      : "";

    this.shadowRoot.innerHTML = `
<style>
:host {
  --sf: var(--card-background-color, #12121a);
  --sf2: #1a1a28;
  --bd: rgba(255,255,255,0.06);
  --tx2: var(--secondary-text-color, #9898a8);
  --dg: #e74c3c;
  --gn: #4ecca3;
  --wn: #f39c12;
  --r: 14px;
  display: block;
  margin-bottom: 20px;
}
.card {
  background: var(--sf);
  border: 1px solid var(--bd);
  border-radius: var(--r);
}
.card-h {
  padding: 14px 18px;
  border-bottom: 1px solid var(--bd);
  font-size: 14px;
  font-weight: 600;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.card-h .count {
  font-weight: 400;
  font-size: 12px;
  color: var(--tx2);
}
.tx-list {
  padding: 6px 18px 12px;
  max-height: 540px;
  overflow-y: auto;
}
.tx-item {
  display: grid;
  grid-template-columns: 56px 1fr auto;
  gap: 12px;
  align-items: flex-start;
  padding: 10px 0;
  border-bottom: 1px solid var(--bd);
  font-size: 13px;
}
.tx-item:last-child { border-bottom: none; }
.tx-date {
  font-size: 11px;
  color: var(--tx2);
  font-variant-numeric: tabular-nums;
  padding-top: 2px;
  white-space: nowrap;
}
.tx-main { min-width: 0; }
.tx-label {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 8px;
}
.tx-sub {
  font-size: 11px;
  color: var(--tx2);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tx-meta {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.tx-cat {
  font-size: 10px;
  color: var(--tx2);
  background: var(--sf2);
  padding: 2px 6px;
  border-radius: 4px;
}
.tx-acc {
  font-size: 10px;
  color: var(--tx2);
}
.tx-pending {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--wn);
  border: 1px solid var(--wn);
  padding: 1px 5px;
  border-radius: 4px;
}
.tx-amount {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  padding-top: 2px;
}
.tx-amount.pos { color: var(--gn); }
.tx-amount.neg { color: var(--dg); }
.tx-toggle {
  display: block;
  margin: 6px auto 0;
  padding: 6px 16px;
  background: transparent;
  border: 1px solid var(--bd);
  border-radius: 8px;
  color: var(--tx2);
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
}
.tx-toggle:hover { color: var(--tx2); border-color: var(--tx2); }
.tx-empty {
  padding: 24px 18px;
  color: var(--tx2);
  font-size: 13px;
  text-align: center;
}
</style>
<div class="card">
  <div class="card-h">
    <span>Importierte Transaktionen</span>
    <span class="count">${total} im Cache</span>
  </div>
  ${total === 0 ? emptyState : `<div class="tx-list">${rows}</div>${toggleBtn}`}
</div>`;

    const btn = this.shadowRoot.getElementById("toggleBtn");
    if (btn) {
      btn.addEventListener("click", () => {
        this._expanded = !this._expanded;
        this._render();
      });
    }
  }

  _formatDate(iso) {
    if (!iso) return "";
    // Expect "YYYY-MM-DD". Fall back to raw string on mismatch.
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
    if (!m) return iso;
    return `${m[3]}.${m[2]}.`;
  }

  _esc(s) {
    if (s === null || s === undefined) return "";
    const d = document.createElement("div");
    d.textContent = String(s);
    return d.innerHTML;
  }
}

customElements.define("fd-transactions-log", FdTransactionsLog);
