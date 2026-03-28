/**
 * fd-recurring-list — Recurring payments card (max 8 shown).
 *
 * Properties:
 *   data {object} — Unified data object from fd-data-provider
 */

const REC_CAT_LABELS = {
  housing: "Wohnen", loans: "Kredite", food: "Lebensmittel", utilities: "Nebenkosten",
  insurance: "Versicherung", subscriptions: "Abos", transport: "Mobilit\u00e4t",
  cleaning: "Reinigung", income: "Einkommen", transfers: "\u00dcbertr\u00e4ge", other: "Sonstiges",
};

class FdRecurringList extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
  }

  set data(v) { this._data = v; this._render(); }

  _render() {
    const d = this._data;
    const recurring = d?.recurring;

    if (!recurring || recurring.length === 0) {
      this.shadowRoot.innerHTML = "";
      return;
    }

    const eur = (v) => new Intl.NumberFormat("de-DE", {
      style: "currency", currency: "EUR",
    }).format(v || 0);

    const items = recurring.slice(0, 8).map(r => {
      const dayStr = r.expected_day ? `${r.expected_day}. d.M.` : "";
      return `<div class="rec-item">
        <div class="rec-left">
          <span>${this._esc(r.creditor)}</span>
          <span class="rec-cat">${this._esc(REC_CAT_LABELS[r.category] || r.category)}</span>
        </div>
        <div style="text-align:right">
          <span class="neg" style="font-weight:600">${eur(Math.abs(r.average_amount))}</span>
          <span class="rec-day">${dayStr}</span>
        </div>
      </div>`;
    }).join("");

    this.shadowRoot.innerHTML = `
<style>
:host {
  --sf: var(--card-background-color, #12121a);
  --sf2: #1a1a28;
  --bd: rgba(255,255,255,0.06);
  --tx2: var(--secondary-text-color, #9898a8);
  --dg: #e74c3c;
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
</style>
<div class="card">
  <div class="card-h">Wiederkehrende Zahlungen
    <span style="font-weight:400;font-size:12px;color:var(--tx2)">${recurring.length} erkannt</span>
  </div>
  <div class="rec-list">${items}</div>
</div>`;
  }

  _esc(s) {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }
}

customElements.define("fd-recurring-list", FdRecurringList);
