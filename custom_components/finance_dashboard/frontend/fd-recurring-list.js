/**
 * fd-recurring-list — Recurring payments card (max 8 shown).
 *
 * Properties:
 *   data {object} — Unified data object from fd-data-provider
 */

// REC_CAT_LABELS comes from window._fd.CAT_LABELS (set by fd-shared-styles.js).

class FdRecurringList extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
  }

  set data(v) { this._data = v; this._render(); }

  _render() {
    const d = this._data;

    // Show skeleton while data has never been set
    if (d === null || d === undefined) {
      this._renderSkeleton();
      return;
    }

    const recurring = d?.recurring;
    if (!recurring || recurring.length === 0) {
      this.shadowRoot.innerHTML = "";
      return;
    }

    const { CAT_LABELS, SHARED_CSS, escHtml, tSync } = window._fd;

    const eur = (v) => new Intl.NumberFormat("de-DE", {
      style: "currency", currency: "EUR",
    }).format(v || 0);

    const items = recurring.slice(0, 8).map(r => {
      const dayStr = r.expected_day ? `${r.expected_day}. d.M.` : "";
      return `<div class="rec-item">
        <div class="rec-left">
          <span>${escHtml(r.creditor)}</span>
          <span class="rec-cat">${escHtml(CAT_LABELS[r.category] || r.category)}</span>
        </div>
        <div style="text-align:right">
          <span class="neg" style="font-weight:600">${eur(Math.abs(r.average_amount))}</span>
          <span class="rec-day">${dayStr}</span>
        </div>
      </div>`;
    }).join("");

    const LOCAL_CSS = `
:host {
  margin-bottom: 20px;
}
.rec-list { padding: 18px; }
.rec-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--bd);
  font-size: 13px;
}
.rec-item:last-child { border-bottom: none; }
.rec-left { display: flex; align-items: center; gap: 8px; }
.rec-cat {
  font-size: 10px;
  color: var(--tx2);
  background: var(--sf2);
  padding: 2px 6px;
  border-radius: 4px;
}
.rec-day { font-size: 11px; color: var(--tx2); }
.neg { color: var(--dg); }
`;

    this.shadowRoot.innerHTML = `
<style>${SHARED_CSS}${LOCAL_CSS}</style>
<div class="card">
  <div class="card-h">${tSync("recurring.title")}
    <span style="font-weight:400;font-size:12px;color:var(--tx2)">${recurring.length} ${tSync("recurring.detected")}</span>
  </div>
  <div class="rec-list">${items}</div>
</div>`;
  }
  _renderSkeleton() {
    const { SHARED_CSS, tSync } = window._fd;
    const shimmerCss = `
@keyframes fd-shimmer {
  0%   { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}
.skeleton-line {
  border-radius: 4px;
  height: 14px;
  background: linear-gradient(90deg, var(--sf2) 25%, rgba(255,255,255,0.06) 50%, var(--sf2) 75%);
  background-size: 800px 100%;
  animation: fd-shimmer 1.4s infinite linear;
  margin-bottom: 6px;
}
`;
    const rows = Array.from({ length: 4 }, (_, i) =>
      `<div class="skeleton-line" style="width:${60 + (i % 3) * 15}%"></div>`
    ).join("");
    this.shadowRoot.innerHTML = `
<style>${SHARED_CSS}${shimmerCss}
:host { margin-bottom: 20px; }
</style>
<div class="card" aria-busy="true" aria-label="${tSync("recurring.loading")}">
  <div class="card-h">${tSync("recurring.title")}</div>
  <div style="padding:18px">${rows}</div>
</div>`;
  }
}

customElements.define("fd-recurring-list", FdRecurringList);
