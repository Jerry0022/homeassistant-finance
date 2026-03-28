/**
 * Finance Dashboard — Sidebar Panel (Phase 2)
 *
 * Full monthly overview using Lovelace card components as building blocks.
 * Privacy-first: only aggregated data shown by default.
 *
 * Update strategy:
 *  - Fetch data once when the panel is first connected to the DOM
 *  - Auto-refresh every 10 minutes via setInterval
 *  - Manual refresh via the "Aktualisieren" button
 *  - Never re-fetch on hass setter calls (hass changes many times per second)
 *
 * CHECKLIST (from design sprint):
 * [x] Total balance from bank accounts (Must)
 * [x] Total income, total expenses, monthly surplus (Must)
 * [x] Savings rate (Must)
 * [x] Category breakdown donut chart (Must)
 * [x] Category bars - percentage of total (Should)
 * [x] Spielgeld per person (Must)
 * [x] Income ratio (Must)
 * [x] Shared fixed costs bar (Must)
 * [x] Top-3 cost drivers (Should)
 * [x] Fixed vs variable costs split (Should)
 * [x] Recurring costs section (Should)
 * [ ] 6-month trend chart (Should — Phase 2.1)
 * [x] Privacy-first: only aggregates (Must)
 * [x] Admin-only transaction details (Must)
 * [x] Dashboard deactivatable in config (Must via Options)
 */

const AUTO_REFRESH_MS = 10 * 60 * 1000; // 10 minutes

class FinanceDashboardPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._refreshInterval = null;
    this._refreshing = false;
  }

  set hass(hass) {
    this._hass = hass;
    // Only build the DOM once — data is loaded separately via _refresh()
    if (!this.shadowRoot.querySelector(".fd")) {
      this._render();
    }
  }

  connectedCallback() {
    // Fetch data immediately when panel enters the DOM
    this._refresh();
    // Then keep it fresh every 10 minutes
    this._startAutoRefresh();
  }

  disconnectedCallback() {
    this._stopAutoRefresh();
  }

  _startAutoRefresh() {
    if (this._refreshInterval) return;
    this._refreshInterval = setInterval(
      () => this._refresh(),
      AUTO_REFRESH_MS
    );
  }

  _stopAutoRefresh() {
    if (this._refreshInterval) {
      clearInterval(this._refreshInterval);
      this._refreshInterval = null;
    }
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
.hdr-right { display:flex; align-items:center; gap:10px; }
.last-update { font-size:11px; color:var(--tx2); }
.btn { padding:7px 14px; border-radius:10px; border:1px solid var(--bd);
  background:var(--sf); color:var(--tx); font-size:13px; cursor:pointer; }
.btn:hover { background:var(--sf2); }
.btn:disabled { opacity:.5; cursor:default; }
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

/* Recurring list */
.rec-list { padding:18px; }
.rec-item { display:flex; justify-content:space-between; align-items:center; padding:8px 0;
  border-bottom:1px solid var(--bd); font-size:13px; }
.rec-item:last-child { border-bottom:none; }
.rec-left { display:flex; align-items:center; gap:8px; }
.rec-cat { font-size:10px; color:var(--tx2); background:var(--sf2); padding:2px 6px; border-radius:4px; }
.rec-day { font-size:11px; color:var(--tx2); }

.loading { text-align:center; padding:60px; color:var(--tx2); }
.error { text-align:center; padding:40px; color:var(--dg); }

/* Responsive */
@media (max-width: 768px) {
  .stats { grid-template-columns: repeat(2, 1fr); }
  .grid { grid-template-columns: 1fr; }
  .donut-wrap { flex-direction: column; }
  .persons { grid-template-columns: 1fr; }
}
</style>

<div class="fd">
  <div class="hdr">
    <h1>Finance Dashboard</h1>
    <div class="hdr-right">
      <span class="last-update" id="lastUpdate"></span>
      <button class="btn" id="monthBtn"></button>
      <button class="btn btn-p" id="refreshBtn">Aktualisieren</button>
    </div>
  </div>
  <div id="content" class="loading">Lade Finanzdaten&#8230;</div>
</div>`;

    this.shadowRoot.getElementById("refreshBtn")
      .addEventListener("click", () => this._refresh());
  }

  async _refresh() {
    if (!this._hass || this._refreshing) return;
    this._refreshing = true;

    const btn = this.shadowRoot.getElementById("refreshBtn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Laden\u2026";
    }

    const c = this.shadowRoot.getElementById("content");
    if (!c) {
      this._refreshing = false;
      return;
    }

    try {
      const [bal, txn, sum] = await Promise.all([
        this._hass.callApi("GET", "finance_dashboard/balances"),
        this._hass.callApi("GET", "finance_dashboard/transactions"),
        this._hass.callApi("GET", "finance_dashboard/summary"),
      ]);
      this._draw(c, bal, txn, sum);
      const ts = this.shadowRoot.getElementById("lastUpdate");
      if (ts) ts.textContent = `Zuletzt: ${new Date().toLocaleTimeString("de-DE")}`;
    } catch (e) {
      console.error("Finance Dashboard refresh error:", e);
      c.className = "error";
      c.innerHTML = `<div>Verbinde dein Bankkonto unter Einstellungen \u2192 Integrationen \u2192 Finance.</div>`;
    } finally {
      this._refreshing = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Aktualisieren";
      }
    }
  }

  _draw(el, balances, txnData, summary) {
    const eur = (v) => new Intl.NumberFormat("de-DE",{style:"currency",currency:"EUR"}).format(v || 0);
    const pct = (v) => `${Math.round(v || 0)}%`;

    const cats = summary?.categories || {};
    const totalExp = summary?.total_expenses || 0;
    const totalInc = summary?.total_income || 0;
    const surplus = summary?.balance || 0;
    const txnCount = summary?.transaction_count || 0;
    const household = summary?.household || null;
    const recurring = summary?.recurring || [];
    const fixedCosts = summary?.fixed_costs || 0;
    const varCosts = summary?.variable_costs || 0;

    // Compute real bank balance from balances API data
    let totalBalance = 0;
    let accountCount = 0;
    if (balances && typeof balances === "object") {
      for (const accId of Object.keys(balances)) {
        const accBals = balances[accId]?.balances || [];
        if (accBals.length > 0) {
          // Pick best balance type (same priority as sensor)
          const bal = this._pickBalance(accBals);
          if (bal) {
            totalBalance += parseFloat(bal.balanceAmount?.amount || 0);
            accountCount++;
          }
        }
      }
    }

    // Month label
    const now = new Date();
    const monthNames = ["Jan","Feb","M\u00e4r","Apr","Mai","Jun","Jul","Aug","Sep","Okt","Nov","Dez"];
    const monthBtn = this.shadowRoot.getElementById("monthBtn");
    if (monthBtn) monthBtn.textContent = `${monthNames[now.getMonth()]} ${now.getFullYear()}`;

    // Category colors
    const catColors = {
      housing:"#3b82f6", loans:"#e74c3c", food:"#f97316", utilities:"#eab308",
      insurance:"#8b5cf6", subscriptions:"#ec4899", transport:"#06b6d4",
      cleaning:"#a855f7", income:"#4ecca3", transfers:"#6b7280", other:"#6b7280"
    };
    const catLabels = {
      housing:"Wohnen", loans:"Kredite", food:"Lebensmittel", utilities:"Nebenkosten",
      insurance:"Versicherung", subscriptions:"Abos", transport:"Mobilit\u00e4t",
      cleaning:"Reinigung", income:"Einkommen", transfers:"\u00dcbertr\u00e4ge", other:"Sonstiges"
    };

    // Sort categories by absolute amount, exclude income/transfers from expense chart
    const sorted = Object.entries(cats)
      .filter(([k]) => k !== "income" && k !== "transfers")
      .sort((a,b) => Math.abs(b[1]) - Math.abs(a[1]));

    // Savings rate
    const savingsRate = totalInc > 0 ? Math.round(surplus / totalInc * 100) : 0;

    // ---- Build HTML ----
    let html = "";

    // Stats row — 4 KPIs
    html += `<div class="stats">
      <div class="stat"><div class="stat-l">Gesamtsaldo</div>
        <div class="stat-v ${totalBalance>=0?"pos":"neg"}">${eur(totalBalance)}</div>
        <div class="stat-d neu">${accountCount} ${accountCount===1?"Konto":"Konten"}</div></div>
      <div class="stat"><div class="stat-l">Ausgaben</div>
        <div class="stat-v neg">${eur(totalExp)}</div>
        <div class="stat-d">${txnCount} Transaktionen</div></div>
      <div class="stat"><div class="stat-l">Einnahmen</div>
        <div class="stat-v" style="color:var(--bl)">${eur(totalInc)}</div>
        <div class="stat-d neu">Netto</div></div>
      <div class="stat"><div class="stat-l">Sparquote</div>
        <div class="stat-v" style="color:var(--pp)">${pct(savingsRate)}</div>
        <div class="stat-d neu">${surplus >= 0 ? "+" : ""}${eur(surplus)} Monatssaldo</div></div>
    </div>`;

    // ---- Person cards (Household split) ----
    if (household && household.members && household.members.length > 0) {
      html += `<div class="persons">`;
      for (const m of household.members) {
        const spielgeldClass = m.spielgeld >= 0 ? "pos" : "neg";
        html += `<div class="person">
          <div class="person-n">${this._esc(m.person)}</div>
          <div class="person-r">Einkommensanteil: ${m.income_ratio.toFixed(1)}% &middot; ${household.split_model === "proportional" ? "Proportional" : household.split_model === "equal" ? "Gleich" : "Benutzerdefiniert"}</div>
          <ul class="person-rows">
            <li class="person-row"><span class="l">Einkommen (netto)</span><span>${eur(m.net_income)}</span></li>
            <li class="person-row"><span class="l">Anteil Fixkosten</span><span class="neg">${eur(m.shared_costs_share)}</span></li>
            <li class="person-row"><span class="l">Eigene Ausgaben</span><span class="neg">${eur(m.individual_costs)}</span></li>
            ${m.bonus_amount > 0 ? `<li class="person-row"><span class="l">Bonus (erkannt)</span><span class="pos">${eur(m.bonus_amount)}</span></li>` : ""}
          </ul>
          <div class="person-saldo">
            <span class="l">Spielgeld</span>
            <span class="v ${spielgeldClass}">${eur(m.spielgeld)}</span>
          </div>
        </div>`;
      }
      html += `</div>`;
    }

    // ---- Category donut + Top 3 + Fix vs Var grid ----
    // Donut segments
    let donutSvg = `<circle cx="50" cy="50" r="40" fill="none" stroke="#222236" stroke-width="12"/>`;
    let offset = 0;
    const circ = 2 * Math.PI * 40;
    for (const [cat, amt] of sorted) {
      const p = totalExp > 0 ? Math.abs(amt) / totalExp : 0;
      const len = p * circ;
      donutSvg += `<circle cx="50" cy="50" r="40" fill="none"
        stroke="${catColors[cat]||"#6b7280"}" stroke-width="12"
        stroke-dasharray="${len} ${circ-len}" stroke-dashoffset="-${offset}"
        transform="rotate(-90 50 50)"/>`;
      offset += len;
    }

    // Category list
    const catList = sorted.map(([cat,amt]) => {
      const p = totalExp > 0 ? Math.round(Math.abs(amt)/totalExp*100) : 0;
      return `<li class="cat-item">
        <div class="cat-dot" style="background:${catColors[cat]||"#6b7280"}"></div>
        <span class="cat-n">${catLabels[cat]||cat}</span>
        <span class="cat-a">${eur(Math.abs(amt))}</span>
        <span class="cat-p">${p}%</span>
      </li>`;
    }).join("");

    // Top 3 cost drivers
    const top3 = sorted.slice(0,3).map(([cat,amt]) =>
      `<div class="top-item"><span>${catLabels[cat]||cat}</span>
       <span class="neg">${eur(Math.abs(amt))}</span></div>`
    ).join("");

    // Fixed vs variable
    const fixPct = totalExp > 0 ? Math.round(fixedCosts/totalExp*100) : 0;
    const varPct = 100 - fixPct;

    html += `<div class="grid">
      <div class="card">
        <div class="card-h">Ausgaben nach Kategorie</div>
        <div class="donut-wrap">
          <div class="donut">
            <svg viewBox="0 0 100 100">${donutSvg}</svg>
            <div class="donut-c"><div class="v">${eur(totalExp)}</div><div class="l">Gesamt</div></div>
          </div>
          <ul class="cat-list">${catList||`<li style="color:var(--tx2);font-size:13px">Keine Ausgaben</li>`}</ul>
        </div>
      </div>
      <div>
        <div class="card" style="margin-bottom:14px">
          <div class="card-h">Top-3 Kostentreiber</div>
          <div class="top-list">${top3||`<div style="color:var(--tx2);font-size:13px;padding:18px">Keine Daten</div>`}</div>
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

    // ---- Shared fixed costs distribution bar ----
    if (household && household.total_shared_costs > 0) {
      const memberColors = ["#3b82f6", "#8b5cf6", "#f97316", "#ec4899", "#06b6d4"];
      const sharedBar = household.members.map((m, i) => {
        const w = household.total_shared_costs > 0
          ? (m.shared_costs_share / household.total_shared_costs * 100)
          : 0;
        return `<div style="width:${w}%;background:${memberColors[i % memberColors.length]}"></div>`;
      }).join("");
      const sharedLegend = household.members.map((m, i) =>
        `<div class="cost-legend-item"><div class="cost-legend-dot" style="background:${memberColors[i % memberColors.length]}"></div>${this._esc(m.person)} ${eur(m.shared_costs_share)} (${m.income_ratio.toFixed(0)}%)</div>`
      ).join("");

      html += `<div class="card" style="margin-bottom:20px">
        <div class="card-h">Geteilte Fixkosten <span style="font-weight:400;font-size:12px;color:var(--tx2)">${eur(household.total_shared_costs)} gesamt</span></div>
        <div style="padding:14px 18px">
          <div class="cost-bar">${sharedBar}</div>
        </div>
        <div class="cost-legend">${sharedLegend}</div>
      </div>`;
    } else {
      // Cost distribution by category when no household
      const costBar = sorted.map(([cat,amt]) => {
        const p = totalExp > 0 ? Math.abs(amt)/totalExp*100 : 0;
        return `<div style="width:${p}%;background:${catColors[cat]||"#6b7280"}"></div>`;
      }).join("");
      const costLegend = sorted.slice(0,6).map(([cat,amt]) =>
        `<div class="cost-legend-item"><div class="cost-legend-dot" style="background:${catColors[cat]||"#6b7280"}"></div>${catLabels[cat]||cat} ${eur(Math.abs(amt))}</div>`
      ).join("");

      html += `<div class="card" style="margin-bottom:20px">
        <div class="card-h">Kostenverteilung</div>
        <div style="padding:14px 18px">
          <div class="cost-bar">${costBar||`<div style="width:100%;background:var(--sf2)"></div>`}</div>
        </div>
        <div class="cost-legend">${costLegend}</div>
      </div>`;
    }

    // ---- Recurring payments ----
    if (recurring && recurring.length > 0) {
      const recItems = recurring.slice(0, 8).map(r => {
        const dayStr = r.expected_day ? `${r.expected_day}. d.M.` : "";
        return `<div class="rec-item">
          <div class="rec-left">
            <span>${this._esc(r.creditor)}</span>
            <span class="rec-cat">${catLabels[r.category] || r.category}</span>
          </div>
          <div style="text-align:right">
            <span class="neg" style="font-weight:600">${eur(Math.abs(r.average_amount))}</span>
            <span class="rec-day">${dayStr}</span>
          </div>
        </div>`;
      }).join("");

      html += `<div class="card" style="margin-bottom:20px">
        <div class="card-h">Wiederkehrende Zahlungen <span style="font-weight:400;font-size:12px;color:var(--tx2)">${recurring.length} erkannt</span></div>
        <div class="rec-list">${recItems}</div>
      </div>`;
    }

    el.className = "";
    el.innerHTML = html;
  }

  /** Pick the most useful balance type from a list of balances. */
  _pickBalance(balances) {
    const priority = ["closingBooked", "interimAvailable", "interimBooked", "closingAvailable"];
    const byType = {};
    for (const b of balances) {
      byType[b.balanceType] = b;
    }
    for (const t of priority) {
      if (byType[t]) return byType[t];
    }
    return balances[0] || null;
  }

  /** Escape HTML to prevent XSS from user-provided names. */
  _esc(s) {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }
}

customElements.define("finance-dashboard-panel", FinanceDashboardPanel);
