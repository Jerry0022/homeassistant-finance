/**
 * fd-category-section — Category donut + top-3 cost drivers + fix vs variable.
 *
 * Properties:
 *   data {object} — Unified data object from fd-data-provider
 */

// CAT_COLORS and CAT_LABELS come from window._fd (set by fd-shared-styles.js).

class FdCategorySection extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
  }

  set data(v) { this._data = v; this._render(); }

  _render() {
    const d = this._data;
    if (d === null || d === undefined) {
      this._renderSkeleton();
      return;
    }

    const { CAT_COLORS, CAT_LABELS, SHARED_CSS, escHtml } = window._fd;

    const eur = (v) => new Intl.NumberFormat("de-DE", {
      style: "currency", currency: "EUR",
    }).format(v || 0);

    const cats = d.summary?.categories || {};
    const totalExp = d.summary?.totalExpenses || 0;
    const fixedCosts = d.summary?.fixedCosts || 0;
    const varCosts = d.summary?.variableCosts || 0;

    const sorted = Object.entries(cats)
      .filter(([k]) => k !== "income" && k !== "transfers")
      .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));

    // Top 3
    const top3 = sorted.slice(0, 3).map(([cat, amt]) =>
      `<div class="top-item">
        <span>${escHtml(CAT_LABELS[cat] || cat)}</span>
        <span class="neg">${eur(Math.abs(amt))}</span>
      </div>`
    ).join("");

    // Fix vs var
    const fixPct = totalExp > 0 ? Math.round(fixedCosts / totalExp * 100) : 0;
    const varPct = 100 - fixPct;

    const LOCAL_CSS = `
:host {
  margin-bottom: 20px;
  container-type: inline-size;
}
.grid {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 16px;
}
@container (max-width: 980px) {
  .grid { grid-template-columns: 1fr; }
}
@media (max-width: 980px) {
  .grid { grid-template-columns: 1fr; }
}
.neg { color: var(--dg); }
.top-list { padding: 18px; }
.top-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid var(--bd);
  font-size: 13px;
}
.top-item:last-child { border-bottom: none; }
.fv { display: flex; gap: 16px; padding: 18px; }
.fv-block { flex: 1; text-align: center; }
.fv-block .v { font-size: 20px; font-weight: 700; }
.fv-block .l { font-size: 11px; color: var(--tx2); }
.fv-bar {
  height: 8px;
  border-radius: 4px;
  overflow: hidden;
  background: var(--sf2);
  margin: 8px 0;
}
`;

    this.shadowRoot.innerHTML = `
<style>${SHARED_CSS}${LOCAL_CSS}</style>

<div class="grid">
  <div class="card">
    <div class="card-h">Ausgaben nach Kategorie</div>
    <fd-donut-chart id="donut"></fd-donut-chart>
  </div>
  <div>
    <div class="card" style="margin-bottom:14px">
      <div class="card-h">Top-3 Kostentreiber</div>
      <div class="top-list">${top3 || `<div style="color:var(--tx2);font-size:13px;padding:18px">Keine Daten</div>`}</div>
    </div>
    <div class="card">
      <div class="card-h">Fix vs. Variabel</div>
      <div class="fv">
        <div class="fv-block">
          <div class="v">${eur(fixedCosts)}</div>
          <div class="l">Fixkosten (${fixPct}%)</div>
          <div class="fv-bar"><div style="width:${fixPct}%;height:100%;background:var(--bl);border-radius:4px"></div></div>
        </div>
        <div class="fv-block">
          <div class="v">${eur(varCosts)}</div>
          <div class="l">Variabel (${varPct}%)</div>
          <div class="fv-bar"><div style="width:${varPct}%;height:100%;background:var(--wn);border-radius:4px"></div></div>
        </div>
      </div>
    </div>
  </div>
</div>`;

    // Pass data to donut chart
    const donut = this.shadowRoot.getElementById("donut");
    if (donut) {
      donut.data = {
        categories: cats,
        totalExpenses: totalExp,
        catColors: CAT_COLORS,
        catLabels: CAT_LABELS,
      };
    }
  }
  _renderSkeleton() {
    const { SHARED_CSS } = window._fd;
    const shimmerCss = `
@keyframes fd-shimmer {
  0%   { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}
.skeleton-line {
  border-radius: 4px;
  background: linear-gradient(90deg, var(--sf2) 25%, rgba(255,255,255,0.06) 50%, var(--sf2) 75%);
  background-size: 800px 100%;
  animation: fd-shimmer 1.4s infinite linear;
  margin-bottom: 10px;
}
.skeleton-circle {
  width: 120px; height: 120px; border-radius: 50%;
  background: linear-gradient(90deg, var(--sf2) 25%, rgba(255,255,255,0.06) 50%, var(--sf2) 75%);
  background-size: 800px 100%;
  animation: fd-shimmer 1.4s infinite linear;
  margin: 20px auto;
}
`;
    this.shadowRoot.innerHTML = `
<style>${SHARED_CSS}${shimmerCss}
:host { margin-bottom: 20px; container-type: inline-size; }
.grid { display: grid; grid-template-columns: 1fr 340px; gap: 16px; }
@container (max-width: 980px) { .grid { grid-template-columns: 1fr; } }
@media (max-width: 980px) { .grid { grid-template-columns: 1fr; } }
</style>
<div class="grid" aria-busy="true" aria-label="Wird geladen…">
  <div class="card"><div class="skeleton-circle"></div>
    <div style="padding:0 20px 20px">
      ${Array.from({ length: 5 }, (_, i) => `<div class="skeleton-line" style="height:12px;width:${50 + i * 10}%"></div>`).join("")}
    </div>
  </div>
  <div>
    <div class="card" style="margin-bottom:14px;padding:18px">
      ${Array.from({ length: 3 }, () => `<div class="skeleton-line" style="height:14px;width:80%"></div>`).join("")}
    </div>
    <div class="card" style="padding:18px">
      ${Array.from({ length: 2 }, () => `<div class="skeleton-line" style="height:20px;width:60%"></div>`).join("")}
    </div>
  </div>
</div>`;
  }
}

customElements.define("fd-category-section", FdCategorySection);
