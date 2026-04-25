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

// TX_CAT_LABELS comes from window._fd.CAT_LABELS (set by fd-shared-styles.js).

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

    const { CAT_LABELS, SHARED_CSS, escHtml, tSync } = window._fd;

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
      const label = t.creditor || t.description || "—";
      const sub = t.creditor && t.description && t.creditor !== t.description
        ? t.description : "";
      const cat = CAT_LABELS[t.category] || t.category || tSync("general.other");
      const dateStr = this._formatDate(t.date);
      const pending = t.status === "pending"
        ? `<span class="tx-pending" title="${tSync("transactions.pending_title")}">${tSync("transactions.pending")}</span>`
        : "";
      const account = t.account_name
        ? `<span class="tx-acc">${escHtml(t.account_name)}</span>`
        : "";

      return `<div class="tx-item">
        <div class="tx-date">${escHtml(dateStr)}</div>
        <div class="tx-main">
          <div class="tx-label">${escHtml(label)} ${pending}</div>
          ${sub ? `<div class="tx-sub">${escHtml(sub)}</div>` : ""}
          <div class="tx-meta">
            <span class="tx-cat">${escHtml(cat)}</span>
            ${account}
          </div>
        </div>
        <div class="tx-amount ${amountClass}">${sign}${eur(amount)}</div>
      </div>`;
    }).join("");

    const toggleBtn = total > DEFAULT_LIMIT
      ? `<button class="tx-toggle" id="toggleBtn">
          ${this._expanded ? tSync("transactions.show_less") : tSync("transactions.show_all", { count: String(total) })}
        </button>`
      : "";

    const emptyState = total === 0
      ? `<div class="tx-empty">${tSync("transactions.empty_cache")}</div>`
      : "";

    const LOCAL_CSS = `
:host {
  margin-bottom: 20px;
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
.tx-amount.pos { color: var(--ac); }
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
`;

    this.shadowRoot.innerHTML = `
<style>${SHARED_CSS}${LOCAL_CSS}</style>
<div class="card">
  <div class="card-h">
    <span>${tSync("transactions.title")}</span>
    <span class="count">${total} ${tSync("transactions.in_cache")}</span>
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
}

customElements.define("fd-transactions-log", FdTransactionsLog);
