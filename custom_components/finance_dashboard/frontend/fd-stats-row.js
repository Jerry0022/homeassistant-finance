/**
 * fd-stats-row — 4-KPI grid: balance, expenses, income, savings rate.
 *
 * Properties:
 *   data {object} — Unified data object from fd-data-provider
 */

class FdStatsRow extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
  }

  set data(v) { this._data = v; this._render(); }

  _render() {
    const d = this._data;
    if (!d) {
      this.shadowRoot.innerHTML = "";
      return;
    }

    const eur = (v) => new Intl.NumberFormat("de-DE", {
      style: "currency", currency: "EUR",
    }).format(v || 0);

    const totalBalance = d.totalBalance || 0;
    const totalExp = d.summary?.totalExpenses || 0;
    const totalInc = d.summary?.totalIncome || 0;
    const surplus = d.summary?.balance || 0;
    const txnCount = d.summary?.transactionCount || 0;
    const accountCount = d.accountCount || 0;
    const savingsRate = totalInc > 0 ? Math.round(surplus / totalInc * 100) : 0;

    this.shadowRoot.innerHTML = `
<style>
:host { display: block; margin-bottom: 20px; }
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}
@media (max-width: 768px) {
  .stats { grid-template-columns: repeat(2, 1fr); }
}
</style>
<div class="stats">
  <fd-stat-card id="balance"></fd-stat-card>
  <fd-stat-card id="expenses"></fd-stat-card>
  <fd-stat-card id="income"></fd-stat-card>
  <fd-stat-card id="savings"></fd-stat-card>
</div>`;

    const balance = this.shadowRoot.getElementById("balance");
    balance.label = "Gesamtsaldo";
    balance.value = eur(totalBalance);
    balance.subtitle = `${accountCount} ${accountCount === 1 ? "Konto" : "Konten"}`;
    balance.accent = "var(--accent-color, #4ecca3)";
    balance.valclass = totalBalance >= 0 ? "pos" : "neg";

    const expenses = this.shadowRoot.getElementById("expenses");
    expenses.label = "Ausgaben";
    expenses.value = eur(totalExp);
    expenses.subtitle = `${txnCount} Transaktionen`;
    expenses.accent = "#e74c3c";
    expenses.valclass = "neg";

    const income = this.shadowRoot.getElementById("income");
    income.label = "Einnahmen";
    income.value = eur(totalInc);
    income.subtitle = "Netto";
    income.accent = "#3b82f6";
    income.valclass = "";

    const savings = this.shadowRoot.getElementById("savings");
    savings.label = "Sparquote";
    savings.value = `${savingsRate}%`;
    savings.subtitle = `${surplus >= 0 ? "+" : ""}${eur(surplus)} Monatssaldo`;
    savings.accent = "#8b5cf6";
    savings.valclass = "";
  }
}

customElements.define("fd-stats-row", FdStatsRow);
