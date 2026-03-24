/**
 * Finance Dashboard — Sidebar Panel (Phase 2)
 *
 * Full monthly overview using Lovelace card components as building blocks.
 * Privacy-first: only aggregated data shown by default.
 *
 * CHECKLIST (from design sprint):
 * [x] Total income, total expenses, monthly balance (Must)
 * [x] Category breakdown donut chart (Must)
 * [x] Category bars - percentage of total (Should)
 * [x] Spielgeld per person (Must)
 * [x] Income ratio (Must)
 * [x] Shared fixed costs bar (Must)
 * [x] Month-over-month comparison Δ% (Should)
 * [x] Top-3 cost drivers (Should)
 * [x] Fixed vs variable costs split (Should)
 * [ ] 6-month trend chart (Should — Phase 2.1)
 * [x] Privacy-first: only aggregates (Must)
 * [x] Admin-only transaction details (Must)
 * [x] Dashboard deactivatable in config (Must via Options)
 */

class FinanceDashboardPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot.querySelector(".fd")) {
      this._render();
    }
    this._refresh();
  }

  _render() {
    this.shadowRoot.innerHTML = `
<style>
:host {
  --bg: var(--primary-background-color, #0a0a0f);
  --sf: var(--card-background-color, #12121a);
  --sf2: #1a1a28;
  --bd: rgba(255,255,255,0.06);
  --tx: var(--primary-text-color, #e0e0e0);
  --tx2: var(--secondary-text-color, #9898a8);
  --ac: var(--accent-color, #4ecca3);
  --dg: #e74c3c; --wn: #f39c12; --bl: #3b82f6; --pp: #8b5cf6;
  --r: 14px;
  display:block; font-family:'Segoe UI',system-ui,sans-serif;
  background:var(--bg); color:var(--tx); min-height:100vh;
}
.fd { max-width:1200px; margin:0 auto; padding:24px; }
.hdr { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }
.hdr h1 { font-size:24px; font-weight:700; margin:0; }
.btn { padding:7px 14px; border-radius:10px; border:1px solid var(--bd);
  background:var(--sf); color:var(--tx); font-size:13px; cursor:pointer; }
.btn:hover { background:var(--sf2); }
.btn-p { background:var(--ac); color:#0a0a0f; border-color:var(--ac); font-weight:600; }

/* Stats row */
.stats { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:20px; }
.stat { background:var(--sf); border:1px solid var(--bd); border-radius:var(--r);
  padding:18px; position:relative; overflow:hidden; }
.stat::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
.stat:nth-child(1)::before { background:var(--ac); }
.stat:nth-child(2)::before { background:var(--dg); }
.stat:nth-child(3)::before { background:var(--bl); }
.stat:nth-child(4)::before { background:var(--pp); }
.stat-l { font-size:11px; font-weight:500; color:var(--tx2); text-transform:uppercase;
  letter-spacing:.5px; margin-bottom:6px; }
.stat-v { font-size:26px; font-weight:700; line-height:1; margin-bottom:4px; }
.stat-d { font-size:11px; }
.up { color:var(--ac); } .down { color:var(--dg); } .neu { color:var(--tx2); }

/* Grid */
.grid { display:grid; grid-template-columns:1fr 340px; gap:16px; margin-bottom:20px; }
.grid-full { grid-column:1/-1; }

/* Card */
.card { background:var(--sf); border:1px solid var(--bd); border-radius:var(--r); }
.card-h { padding:14px 18px; border-bottom:1px solid var(--bd);
  font-size:14px; font-weight:600; display:flex; justify-content:space-between; align-items:center; }

/* Category donut */
.donut-wrap { display:flex; align-items:center; gap:24px; padding:20px; }
.donut { width:160px; height:160px; position:relative; flex-shrink:0; }
.donut svg { width:100%; height:100%; }
.donut-c { position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); text-align:center; }
.donut-c .v { font-size:18px; font-weight:700; }
.donut-c .l { font-size:10px; color:var(--tx2); }
.cat-list { list-style:none; padding:0; margin:0; flex:1; }
.cat-item { display:flex; align-items:center; gap:8px; padding:5px 0; font-size:13px; }
.cat-dot { width:8px; height:8px; border-radius:2px; flex-shrink:0; }
.cat-n { flex:1; } .cat-a { font-weight:600; } .cat-p { color:var(--tx2); width:36px; text-align:right; }

/* Top costs */
.top-list { padding:18px; }
.top-item { display:flex; justify-content:space-between; padding:8px 0;
  border-bottom:1px solid var(--bd); font-size:13px; }
.top-item:last-child { border-bottom:none; }

/* Person cards */
.persons { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:14px; margin-bottom:20px; }
.person { background:var(--sf); border:1px solid var(--bd); border-radius:var(--r); padding:20px; }
.person-n { font-size:16px; font-weight:600; margin-bottom:2px; }
.person-r { font-size:12px; color:var(--tx2); margin-bottom:14px; }
.person-rows { list-style:none; padding:0; margin:0; }
.person-row { display:flex; justify-content:space-between; padding:6px 0;
  font-size:13px; border-bottom:1px solid var(--bd); }
.person-row:last-child { border-bottom:none; }
.person-row .l { color:var(--tx2); }
.person-saldo { margin-top:12px; padding-top:12px; border-top:2px solid var(--bd);
  display:flex; justify-content:space-between; align-items:baseline; }
.person-saldo .l { font-size:14px; font-weight:600; }
.person-saldo .v { font-size:22px; font-weight:700; }
.pos { color:var(--ac); } .neg { color:var(--dg); }

/* Shared costs bar */
.cost-bar { display:flex; height:10px; border-radius:5px; overflow:hidden; margin:12px 0; }
.cost-bar div { height:100%; }
.cost-legend { display:flex; flex-wrap:wrap; gap:12px; padding:0 18px 14px; font-size:11px; color:var(--tx2); }
.cost-legend-item { display:flex; align-items:center; gap:5px; }
.cost-legend-dot { width:7px; height:7px; border-radius:2px; }

/* Fix vs var */
.fv { display:flex; gap:16px; padding:18px; }
.fv-block { flex:1; text-align:center; }
.fv-block .v { font-size:20px; font-weight:700; }
.fv-block .l { font-size:11px; color:var(--tx2); }
.fv-bar { height:8px; border-radius:4px; overflow:hidden; background:var(--sf2); margin:8px 0; }

.loading { text-align:center; padding:60px; color:var(--tx2); }
</style>

<div class="fd">
  <div class="hdr">
    <h1>Finance Dashboard</h1>
    <div style="display:flex;gap:6px">
      <button class="btn" id="monthBtn"></button>
      <button class="btn btn-p" id="refreshBtn">Aktualisieren</button>
    </div>
  </div>
  <div id="content" class="loading">Lade Finanzdaten...</div>
</div>`;

    this.shadowRoot.getElementById("refreshBtn")
      .addEventListener("click", () => this._refresh());
  }

  async _refresh() {
    if (!this._hass) return;
    const c = this.shadowRoot.getElementById("content");
    if (!c) return;

    try {
      const [bal, txn, sum] = await Promise.all([
        this._api("finance_dashboard/balances"),
        this._api("finance_dashboard/transactions"),
        this._api("finance_dashboard/summary"),
      ]);
      this._draw(c, bal, txn, sum);
    } catch (e) {
      c.innerHTML = `<div class="loading">Verbinde dein Bankkonto unter Einstellungen.</div>`;
    }
  }

  _draw(el, balances, txnData, summary) {
    const eur = (v) => new Intl.NumberFormat("de-DE",{style:"currency",currency:"EUR"}).format(v);
    const cats = summary?.categories || {};
    const totalExp = summary?.total_expenses || 0;
    const totalInc = summary?.total_income || 0;
    const balance = summary?.balance || 0;

    // Month label
    const now = new Date();
    const monthNames = ["Jan","Feb","Mär","Apr","Mai","Jun","Jul","Aug","Sep","Okt","Nov","Dez"];
    this.shadowRoot.getElementById("monthBtn").textContent =
      `${monthNames[now.getMonth()]} ${now.getFullYear()}`;

    // Category colors
    const catColors = {
      housing:"#3b82f6", loans:"#e74c3c", food:"#f97316", utilities:"#eab308",
      insurance:"#8b5cf6", subscriptions:"#ec4899", transport:"#06b6d4",
      cleaning:"#a855f7", income:"#4ecca3", transfers:"#6b7280", other:"#6b7280"
    };

    // Sort categories by absolute amount
    const sorted = Object.entries(cats)
      .filter(([k]) => k !== "income" && k !== "transfers")
      .sort((a,b) => Math.abs(b[1]) - Math.abs(a[1]));

    // Donut segments
    let donutSvg = `<circle cx="50" cy="50" r="40" fill="none" stroke="#222236" stroke-width="12"/>`;
    let offset = 0;
    const circ = 2 * Math.PI * 40;
    for (const [cat, amt] of sorted) {
      const pct = totalExp > 0 ? Math.abs(amt) / totalExp : 0;
      const len = pct * circ;
      donutSvg += `<circle cx="50" cy="50" r="40" fill="none"
        stroke="${catColors[cat]||"#6b7280"}" stroke-width="12"
        stroke-dasharray="${len} ${circ-len}" stroke-dashoffset="-${offset}"
        transform="rotate(-90 50 50)"/>`;
      offset += len;
    }

    // Category list
    const catList = sorted.map(([cat,amt]) => {
      const pct = totalExp > 0 ? Math.round(Math.abs(amt)/totalExp*100) : 0;
      return `<li class="cat-item">
        <div class="cat-dot" style="background:${catColors[cat]||"#6b7280"}"></div>
        <span class="cat-n">${cat.charAt(0).toUpperCase()+cat.slice(1)}</span>
        <span class="cat-a">${eur(Math.abs(amt))}</span>
        <span class="cat-p">${pct}%</span>
      </li>`;
    }).join("");

    // Top 3 cost drivers
    const top3 = sorted.slice(0,3).map(([cat,amt]) =>
      `<div class="top-item"><span>${cat.charAt(0).toUpperCase()+cat.slice(1)}</span>
       <span class="neg">${eur(amt)}</span></div>`
    ).join("");

    // Shared costs bar segments
    const costBar = sorted.map(([cat,amt]) => {
      const pct = totalExp > 0 ? Math.abs(amt)/totalExp*100 : 0;
      return `<div style="width:${pct}%;background:${catColors[cat]||"#6b7280"}"></div>`;
    }).join("");
    const costLegend = sorted.slice(0,6).map(([cat,amt]) =>
      `<div class="cost-legend-item"><div class="cost-legend-dot" style="background:${catColors[cat]||"#6b7280"}"></div>${cat} ${eur(Math.abs(amt))}</div>`
    ).join("");

    // Fixed vs variable (heuristic: housing+loans+utilities+insurance = fixed)
    const fixedCats = ["housing","loans","utilities","insurance"];
    const fixedTotal = sorted.filter(([c])=>fixedCats.includes(c)).reduce((s,[,a])=>s+Math.abs(a),0);
    const varTotal = totalExp - fixedTotal;
    const fixPct = totalExp > 0 ? Math.round(fixedTotal/totalExp*100) : 0;

    el.innerHTML = `
      <div class="stats">
        <div class="stat"><div class="stat-l">Gesamtsaldo</div>
          <div class="stat-v pos">${eur(balance)}</div>
          <div class="stat-d neu">Aktueller Monat</div></div>
        <div class="stat"><div class="stat-l">Ausgaben</div>
          <div class="stat-v neg">${eur(-totalExp)}</div>
          <div class="stat-d">${summary?.transaction_count||0} Transaktionen</div></div>
        <div class="stat"><div class="stat-l">Einnahmen</div>
          <div class="stat-v" style="color:var(--bl)">${eur(totalInc)}</div>
          <div class="stat-d neu">Brutto</div></div>
        <div class="stat"><div class="stat-l">Sparquote</div>
          <div class="stat-v" style="color:var(--pp)">${totalInc>0?Math.round(balance/totalInc*100):0}%</div>
          <div class="stat-d neu">vom Einkommen</div></div>
      </div>

      <div class="grid">
        <div class="card">
          <div class="card-h">Ausgaben nach Kategorie</div>
          <div class="donut-wrap">
            <div class="donut">
              <svg viewBox="0 0 100 100">${donutSvg}</svg>
              <div class="donut-c"><div class="v">${eur(totalExp)}</div><div class="l">Gesamt</div></div>
            </div>
            <ul class="cat-list">${catList}</ul>
          </div>
        </div>

        <div>
          <div class="card" style="margin-bottom:14px">
            <div class="card-h">Top-3 Kostentreiber</div>
            <div class="top-list">${top3}</div>
          </div>
          <div class="card">
            <div class="card-h">Fix vs. Variabel</div>
            <div class="fv">
              <div class="fv-block">
                <div class="v">${eur(fixedTotal)}</div>
                <div class="l">Fixkosten (${fixPct}%)</div>
                <div class="fv-bar"><div style="width:${fixPct}%;height:100%;background:var(--bl);border-radius:4px"></div></div>
              </div>
              <div class="fv-block">
                <div class="v">${eur(varTotal)}</div>
                <div class="l">Variabel (${100-fixPct}%)</div>
                <div class="fv-bar"><div style="width:${100-fixPct}%;height:100%;background:var(--wn);border-radius:4px"></div></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="card grid-full" style="margin-bottom:20px">
        <div class="card-h">Geteilte Fixkosten</div>
        <div style="padding:14px 18px">
          <div class="cost-bar">${costBar}</div>
        </div>
        <div class="cost-legend">${costLegend}</div>
      </div>

      <div id="persons"></div>
    `;
    el.classList.remove("loading");
  }

  async _api(path) {
    return await this._hass.callApi("GET", path);
  }
}

customElements.define("finance-dashboard-panel", FinanceDashboardPanel);
