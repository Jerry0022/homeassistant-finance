/**
 * fd-donut-chart — SVG donut chart with category legend.
 *
 * Properties:
 *   data {object} — { categories, totalExpenses, catColors, catLabels }
 */

class FdDonutChart extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
  }

  set data(v) { this._data = v; this._render(); }

  _render() {
    if (!this._data) {
      this.shadowRoot.innerHTML = "";
      return;
    }

    const { categories = {}, totalExpenses = 0 } = this._data;
    const catColors = this._data.catColors || {};
    const catLabels = this._data.catLabels || {};

    const eur = (v) => new Intl.NumberFormat("de-DE", {
      style: "currency", currency: "EUR",
    }).format(v || 0);

    // Sort categories by absolute amount, exclude income/transfers
    const sorted = Object.entries(categories)
      .filter(([k]) => k !== "income" && k !== "transfers")
      .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));

    // Build SVG donut segments
    let donutSvg = `<circle cx="50" cy="50" r="40" fill="none" stroke="#222236" stroke-width="12"/>`;
    let offset = 0;
    const circ = 2 * Math.PI * 40;
    for (const [cat, amt] of sorted) {
      const p = totalExpenses > 0 ? Math.abs(amt) / totalExpenses : 0;
      const len = p * circ;
      donutSvg += `<circle cx="50" cy="50" r="40" fill="none"
        stroke="${catColors[cat] || "#6b7280"}" stroke-width="12"
        stroke-dasharray="${len} ${circ - len}" stroke-dashoffset="-${offset}"
        transform="rotate(-90 50 50)"/>`;
      offset += len;
    }

    // Category legend
    const catList = sorted.map(([cat, amt]) => {
      const p = totalExpenses > 0 ? Math.round(Math.abs(amt) / totalExpenses * 100) : 0;
      return `<li class="cat-item">
        <div class="cat-dot" style="background:${catColors[cat] || "#6b7280"}"></div>
        <span class="cat-n">${this._esc(catLabels[cat] || cat)}</span>
        <span class="cat-a">${eur(Math.abs(amt))}</span>
        <span class="cat-p">${p}%</span>
      </li>`;
    }).join("");

    this.shadowRoot.innerHTML = `
<style>
:host {
  --tx2: var(--secondary-text-color, #9898a8);
  display: block;
}
.donut-wrap {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 20px;
}
.donut {
  width: 160px;
  height: 160px;
  position: relative;
  flex-shrink: 0;
}
.donut svg { width: 100%; height: 100%; }
.donut-c {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
}
.donut-c .v { font-size: 18px; font-weight: 700; }
.donut-c .l { font-size: 10px; color: var(--tx2); }
.cat-list { list-style: none; padding: 0; margin: 0; flex: 1; }
.cat-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  font-size: 13px;
}
.cat-dot { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }
.cat-n { flex: 1; }
.cat-a { font-weight: 600; }
.cat-p { color: var(--tx2); width: 36px; text-align: right; }
@media (max-width: 768px) {
  .donut-wrap { flex-direction: column; }
}
</style>
<div class="donut-wrap">
  <div class="donut">
    <svg viewBox="0 0 100 100">${donutSvg}</svg>
    <div class="donut-c">
      <div class="v">${eur(totalExpenses)}</div>
      <div class="l">Gesamt</div>
    </div>
  </div>
  <ul class="cat-list">${catList || `<li style="color:var(--tx2);font-size:13px">Keine Ausgaben</li>`}</ul>
</div>`;
  }

  _esc(s) {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }
}

customElements.define("fd-donut-chart", FdDonutChart);
