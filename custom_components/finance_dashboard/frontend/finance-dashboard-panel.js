/**
 * Finance — Sidebar Panel (Phase 2)
 *
 * Full monthly overview with integrated setup wizard overlay.
 * Privacy-first: only aggregated data shown by default.
 */

class FinanceDashboardPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._panel = null;
    this._configured = null; // null = unknown, true/false after status check
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot.querySelector(".fd")) {
      this._render();
    }
    this._refresh();
  }

  set panel(panel) {
    this._panel = panel;
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
.btn-icon { padding:7px; border-radius:10px; border:1px solid var(--bd);
  background:var(--sf); color:var(--tx2); cursor:pointer; display:flex; align-items:center; justify-content:center; }
.btn-icon:hover { background:var(--sf2); color:var(--tx); }
.btn-icon svg { width:18px; height:18px; }

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

/* Empty state */
.empty-state { background:var(--sf); border:1px solid var(--bd); border-radius:var(--r);
  padding:48px 24px; text-align:center; }
.empty-icon { margin-bottom:16px; opacity:.8; }
.empty-title { font-size:18px; font-weight:600; margin-bottom:8px; }
.empty-desc { font-size:14px; color:var(--tx2); max-width:360px; margin:0 auto; line-height:1.5; }

/* Refresh indicator */
.refresh-indicator { display:flex; align-items:center; gap:6px; font-size:11px; color:var(--tx2); }
.refresh-indicator .ts { opacity:.7; }
@keyframes pulse-dot { 0%,100% { opacity:.4; } 50% { opacity:1; } }
.refresh-dot { width:6px; height:6px; border-radius:50%; background:var(--ac); display:none; }
.refresh-dot.active { display:inline-block; animation:pulse-dot 1s ease-in-out infinite; }

.loading { text-align:center; padding:60px; color:var(--tx2); }

/* Skeleton loading */
@keyframes shimmer {
  0% { background-position:-400px 0; }
  100% { background-position:400px 0; }
}
.skel { border-radius:var(--r); background:linear-gradient(90deg,var(--sf) 25%,var(--sf2) 50%,var(--sf) 75%);
  background-size:800px 100%; animation:shimmer 1.8s infinite ease-in-out; }
.skel-stats { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:20px; }
.skel-stat { height:100px; }
.skel-grid { display:grid; grid-template-columns:1fr 340px; gap:16px; margin-bottom:20px; }
.skel-card-lg { height:260px; }
.skel-card-sm { height:120px; margin-bottom:14px; }
.skel-card-sm2 { height:126px; }
.skel-bar { height:80px; margin-bottom:20px; }

/* Transaction list */
.txn-list { padding:0; }
.txn-row { display:flex; align-items:center; gap:10px; padding:10px 18px;
  border-bottom:1px solid var(--bd); font-size:13px; }
.txn-row:last-child { border-bottom:none; }
.txn-row.intermediate { opacity:.4; }
.txn-date { width:70px; color:var(--tx2); flex-shrink:0; }
.txn-desc { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.txn-acct { font-size:11px; color:var(--tx2); }
.txn-amt { font-weight:600; width:90px; text-align:right; flex-shrink:0; }
.txn-chain-badge { display:inline-flex; align-items:center; gap:3px; padding:2px 7px;
  border-radius:6px; font-size:10px; font-weight:600; cursor:pointer;
  background:rgba(78,204,163,0.12); color:var(--ac); border:1px solid rgba(78,204,163,0.2); }
.txn-chain-badge:hover { background:rgba(78,204,163,0.22); }
.txn-chain-badge.unconfirmed { background:rgba(243,156,18,0.12); color:var(--wn);
  border-color:rgba(243,156,18,0.2); }
.txn-refund-badge { display:inline-flex; align-items:center; gap:3px; padding:2px 7px;
  border-radius:6px; font-size:10px; font-weight:600;
  background:rgba(59,130,246,0.12); color:var(--bl); border:1px solid rgba(59,130,246,0.2); }
.txn-show-more { text-align:center; padding:10px; }
.txn-show-more button { background:none; border:1px solid var(--bd); color:var(--tx2);
  padding:6px 16px; border-radius:8px; cursor:pointer; font-size:12px; }
.txn-show-more button:hover { background:var(--sf2); }

/* Chain detail overlay */
.chain-overlay { position:fixed; top:0; left:0; right:0; bottom:0; z-index:998;
  background:rgba(0,0,0,0.6); display:flex; justify-content:center; align-items:center; }
.chain-detail { background:var(--sf); border:1px solid var(--bd); border-radius:16px;
  max-width:480px; width:calc(100% - 32px); padding:24px; }
.chain-title { font-size:16px; font-weight:700; margin-bottom:16px; }
.chain-flow { display:flex; flex-direction:column; gap:0; margin-bottom:18px; }
.chain-step { display:flex; align-items:center; gap:10px; padding:10px 0; }
.chain-arrow { color:var(--tx2); font-size:18px; text-align:center; padding:2px 0; }
.chain-role { display:inline-block; padding:2px 6px; border-radius:4px; font-size:10px; font-weight:600; }
.chain-role.source { background:rgba(78,204,163,0.15); color:var(--ac); }
.chain-role.intermediate { background:rgba(243,156,18,0.15); color:var(--wn); }
.chain-role.destination { background:rgba(59,130,246,0.15); color:var(--bl); }
.chain-confidence { font-size:12px; color:var(--tx2); margin-bottom:14px; }
.chain-actions { display:flex; gap:10px; }
.chain-actions .btn { flex:1; text-align:center; }

/* Responsive */
@media(max-width:900px) {
  .fd { padding:16px; }
  .stats { grid-template-columns:repeat(2,1fr); gap:10px; }
  .grid { grid-template-columns:1fr; }
  .skel-stats { grid-template-columns:repeat(2,1fr); }
  .skel-grid { grid-template-columns:1fr; }
  .donut-wrap { flex-direction:column; align-items:stretch; }
  .donut { margin:0 auto; }
  .fv { flex-direction:column; gap:12px; }
  .persons { grid-template-columns:1fr !important; }
}
@media(max-width:480px) {
  .fd { padding:12px; }
  .hdr h1 { font-size:20px; }
  .stats { grid-template-columns:1fr 1fr; gap:8px; }
  .stat { padding:14px; }
  .stat-v { font-size:20px; }
  .stat-l { font-size:10px; }
  .btn { padding:6px 10px; font-size:12px; }
  .card-h { padding:12px 14px; font-size:13px; }
  .donut { width:130px; height:130px; }
  .donut-c .v { font-size:15px; }
  .cat-item { font-size:12px; }
  .top-item { font-size:12px; }
  .cost-legend { padding:0 14px 12px; gap:8px; font-size:10px; }
  .person { padding:16px; }
  .person-saldo .v { font-size:18px; }
  .wizard { border-radius:12px; }
  .wiz-header { padding:20px 20px 0; }
  .wiz-body { padding:0 20px 20px; }
  .skel-stats { grid-template-columns:1fr 1fr; gap:8px; }
  .skel-stat { height:80px; }
}

/* ============ Setup Wizard Overlay ============ */
.overlay {
  position:fixed; top:0; left:0; right:0; bottom:0; z-index:999;
  background:rgba(0,0,0,0.75); display:flex; justify-content:center; align-items:center;
}
.wizard {
  background:var(--sf); border:1px solid var(--bd); border-radius:16px;
  max-width:560px; width:calc(100% - 32px); max-height:calc(100vh - 64px);
  overflow-y:auto; padding:0;
}
.wiz-header {
  padding:24px 28px 0; text-align:center;
}
.wiz-header h2 { font-size:20px; font-weight:700; margin:0 0 4px; }
.wiz-header p { font-size:13px; color:var(--tx2); margin:0; }

/* Step indicator */
.steps { display:flex; justify-content:center; gap:8px; padding:16px 0 20px; }
.step-dot { width:10px; height:10px; border-radius:50%; background:var(--sf2); border:2px solid var(--bd); transition:all .2s; }
.step-dot.active { background:var(--ac); border-color:var(--ac); }
.step-dot.done { background:var(--ac); border-color:var(--ac); opacity:.5; }

.wiz-body { padding:0 28px 24px; }

/* Bank search */
.search-input {
  width:100%; padding:10px 14px; border-radius:10px; border:1px solid var(--bd);
  background:var(--sf2); color:var(--tx); font-size:14px; margin-bottom:12px;
  box-sizing:border-box; outline:none;
}
.search-input:focus { border-color:var(--ac); }
.search-input::placeholder { color:var(--tx2); }
.bank-list { max-height:320px; overflow-y:auto; }
.bank-item {
  display:flex; align-items:center; gap:12px; padding:10px 14px;
  border-radius:10px; cursor:pointer; transition:background .15s;
}
.bank-item:hover { background:var(--sf2); }
.bank-item.selected { background:var(--sf2); border:1px solid var(--ac); }
.bank-logo { width:32px; height:32px; border-radius:6px; object-fit:contain; background:#fff; flex-shrink:0; }
.bank-logo-placeholder { width:32px; height:32px; border-radius:6px; background:var(--sf2);
  display:flex; align-items:center; justify-content:center; font-size:14px; font-weight:700; color:var(--tx2); flex-shrink:0; }
.bank-name { font-size:14px; font-weight:500; }
.bank-bic { font-size:11px; color:var(--tx2); }

/* Waiting state */
.wait-center { text-align:center; padding:32px 0; }
.spinner { width:40px; height:40px; border:3px solid var(--bd); border-top-color:var(--ac);
  border-radius:50%; animation:spin 1s linear infinite; margin:0 auto 16px; }
@keyframes spin { to { transform:rotate(360deg); } }

/* Account assignment */
.acc-item { background:var(--sf2); border-radius:10px; padding:14px; margin-bottom:10px; }
.acc-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
.acc-name { font-size:14px; font-weight:600; }
.acc-iban { font-size:12px; color:var(--tx2); }
.acc-fields { display:flex; flex-direction:column; gap:8px; }
.acc-fields-row { display:flex; gap:10px; }
.acc-fields select, .acc-fields input {
  padding:7px 10px; border-radius:8px; border:1px solid var(--bd);
  background:var(--sf); color:var(--tx); font-size:13px; flex:1;
}
.acc-users-label { font-size:12px; color:var(--tx2); margin-bottom:2px; }
.acc-users-chips { display:flex; flex-wrap:wrap; gap:6px; }
.acc-user-chip { display:inline-flex; align-items:center; gap:4px; padding:4px 10px;
  border-radius:16px; font-size:12px; cursor:pointer; transition:all .15s;
  border:1px solid var(--bd); background:var(--sf); color:var(--tx); }
.acc-user-chip.selected { background:var(--accent-color, #4ecca3); color:#fff; border-color:transparent; }

/* ============ Settings / Manage Overlay ============ */
.manage-list { max-height:400px; overflow-y:auto; }
.manage-acc { background:var(--sf2); border-radius:10px; padding:14px; margin-bottom:10px; }
.manage-acc-hdr { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }
.manage-acc-bank { display:flex; align-items:center; gap:8px; }
.manage-acc-bank img { width:24px; height:24px; border-radius:4px; object-fit:contain; background:#fff; }
.manage-acc-bank span { font-size:12px; color:var(--tx2); }
.manage-acc-iban { font-size:12px; color:var(--tx2); }
.manage-fields { display:flex; flex-direction:column; gap:8px; }
.manage-field-row { display:flex; gap:10px; align-items:center; }
.manage-field-row label { font-size:12px; color:var(--tx2); min-width:60px; }
.manage-field-row input, .manage-field-row select {
  padding:7px 10px; border-radius:8px; border:1px solid var(--bd);
  background:var(--sf); color:var(--tx); font-size:13px; flex:1; }
.manage-add-btn { display:flex; align-items:center; justify-content:center; gap:8px;
  padding:14px; border-radius:10px; border:2px dashed var(--bd); background:transparent;
  color:var(--tx2); font-size:14px; cursor:pointer; width:100%; margin-top:4px; transition:all .15s; }
.manage-add-btn:hover { border-color:var(--ac); color:var(--ac); }
.manage-add-btn svg { width:18px; height:18px; }
.acc-user-chip:hover { opacity:.85; }

/* Buttons */
.wiz-actions { display:flex; justify-content:flex-end; gap:8px; padding-top:16px; }
.wiz-btn { padding:10px 20px; border-radius:10px; border:none; font-size:14px;
  font-weight:600; cursor:pointer; transition:opacity .15s; }
.wiz-btn:hover { opacity:.9; }
.wiz-btn:disabled { opacity:.4; cursor:default; }
.wiz-btn-primary { background:var(--ac); color:#0a0a0f; }
.wiz-btn-secondary { background:var(--sf2); color:var(--tx); border:1px solid var(--bd); }

.error-msg { color:var(--dg); font-size:13px; padding:8px 0; }
.bank-count { font-size:12px; color:var(--tx2); margin-bottom:8px; }
</style>

<div class="fd">
  <div class="hdr">
    <h1>Finance</h1>
    <div style="display:flex;align-items:center;gap:10px">
      <div class="refresh-indicator">
        <span class="refresh-dot" id="refreshDot"></span>
        <span class="ts" id="lastUpdate"></span>
      </div>
      <button class="btn" id="monthBtn"></button>
      <button class="btn btn-p" id="refreshBtn">Aktualisieren</button>
      <button class="btn-icon" id="settingsBtn" title="Konten verwalten">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
          <circle cx="12" cy="12" r="3"/>
        </svg>
      </button>
    </div>
  </div>
  <div id="content"></div>
  <div id="overlay-container"></div>
</div>`;

    this.shadowRoot.getElementById("refreshBtn")
      .addEventListener("click", () => this._refresh());
    this.shadowRoot.getElementById("settingsBtn")
      .addEventListener("click", () => this._showManageOverlay());
    // Show skeleton immediately
    const c = this.shadowRoot.getElementById("content");
    if (c) c.innerHTML = this._renderSkeleton();
  }

  _renderSkeleton() {
    return `
      <div class="skel-stats">
        <div class="skel skel-stat"></div>
        <div class="skel skel-stat"></div>
        <div class="skel skel-stat"></div>
        <div class="skel skel-stat"></div>
      </div>
      <div class="skel-grid">
        <div class="skel skel-card-lg"></div>
        <div>
          <div class="skel skel-card-sm"></div>
          <div class="skel skel-card-sm2"></div>
        </div>
      </div>
      <div class="skel skel-bar"></div>`;
  }

  _setRefreshing(active) {
    const dot = this.shadowRoot.getElementById("refreshDot");
    const btn = this.shadowRoot.getElementById("refreshBtn");
    if (dot) dot.classList.toggle("active", active);
    if (btn) {
      btn.disabled = active;
      btn.textContent = active ? "Wird geladen..." : "Aktualisieren";
    }
  }

  _updateTimestamp() {
    const el = this.shadowRoot.getElementById("lastUpdate");
    if (!el) return;
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    el.textContent = `Stand ${hh}:${mm}`;
    this._lastUpdateTime = now;
  }

  async _refresh() {
    if (!this._hass) return;
    const c = this.shadowRoot.getElementById("content");
    if (!c) return;

    // Show skeleton on first load, keep last data visible on subsequent refreshes
    const hasData = c.querySelector(".stats");
    if (!hasData) {
      c.innerHTML = this._renderSkeleton();
    }

    // Show async refresh indicator
    this._setRefreshing(true);

    // Check setup status first
    try {
      const status = await this._hass.callApi("GET", "finance_dashboard/setup/status");
      this._configured = status.configured;

      if (!status.configured) {
        c.innerHTML = this._renderEmptyDashboard();
        this._setRefreshing(false);
        this._showSetupWizard();
        return;
      }
    } catch (e) {
      // Status endpoint failed — show empty state
      if (!hasData) c.innerHTML = this._renderEmptyDashboard();
      this._setRefreshing(false);
      return;
    }

    // Hide wizard if configured
    this._hideSetupWizard();

    // Load dashboard data
    try {
      const [bal, txn, sum, chains] = await Promise.all([
        this._hass.callApi("GET", "finance_dashboard/balances"),
        this._hass.callApi("GET", "finance_dashboard/transactions"),
        this._hass.callApi("GET", "finance_dashboard/summary"),
        this._hass.callApi("GET", "finance_dashboard/transfer_chains").catch(() => ({ chains: [] })),
      ]);
      this._chainData = chains?.chains || [];
      this._draw(c, bal, txn, sum);
      this._updateTimestamp();
    } catch (e) {
      if (!hasData) c.innerHTML = this._renderEmptyDashboard();
    } finally {
      this._setRefreshing(false);
    }
  }

  _renderEmptyDashboard() {
    const eur = () => new Intl.NumberFormat("de-DE",{style:"currency",currency:"EUR"}).format(0);
    return `
      <div class="stats">
        <div class="stat"><div class="stat-l">Gesamtsaldo</div>
          <div class="stat-v neu">${eur()}</div>
          <div class="stat-d neu">Keine Daten</div></div>
        <div class="stat"><div class="stat-l">Ausgaben</div>
          <div class="stat-v neu">${eur()}</div>
          <div class="stat-d neu">—</div></div>
        <div class="stat"><div class="stat-l">Einnahmen</div>
          <div class="stat-v neu">${eur()}</div>
          <div class="stat-d neu">—</div></div>
        <div class="stat"><div class="stat-l">Sparquote</div>
          <div class="stat-v neu">—</div>
          <div class="stat-d neu">—</div></div>
      </div>
      <div class="empty-state">
        <div class="empty-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--ac)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <rect x="2" y="5" width="20" height="14" rx="2"/>
            <path d="M2 10h20"/>
          </svg>
        </div>
        <div class="empty-title">Bank verbinden</div>
        <div class="empty-desc">Verbinde dein Bankkonto, um Salden, Ausgaben und Budget-Analysen live zu sehen.</div>
      </div>`;
  }

  // ==================== Setup Wizard ====================

  _showSetupWizard() {
    const container = this.shadowRoot.getElementById("overlay-container");
    if (!container || container.querySelector(".overlay")) return;

    this._wizardStep = 1;
    this._wizardInstitutions = [];
    this._wizardSelectedBank = null;
    this._wizardAccounts = [];
    this._wizardHaUsers = [];
    this._wizardPollTimer = null;
    this._wizardLoadError = null;

    container.innerHTML = `<div class="overlay"><div class="wizard" id="wizard"></div></div>`;
    this._renderWizardStep();
    this._loadInstitutions();
    this._loadHaUsers();
  }

  _hideSetupWizard() {
    const container = this.shadowRoot.getElementById("overlay-container");
    if (container) container.innerHTML = "";
    if (this._wizardPollTimer) {
      clearInterval(this._wizardPollTimer);
      this._wizardPollTimer = null;
    }
  }

  _renderWizardStep() {
    const wiz = this.shadowRoot.getElementById("wizard");
    if (!wiz) return;

    const stepDots = [1,2,3].map(s => {
      let cls = "step-dot";
      if (s === this._wizardStep) cls += " active";
      else if (s < this._wizardStep) cls += " done";
      return `<div class="${cls}"></div>`;
    }).join("");

    const titles = {
      1: { h: "Bank verbinden", p: "Wähle deine Bank aus der Liste" },
      2: { h: "Bankfreigabe", p: "Autorisiere den Zugriff bei deiner Bank" },
      3: { h: "Konten zuweisen", p: "Ordne deine Konten Personen zu" },
    };

    const t = titles[this._wizardStep];

    let body = "";
    if (this._wizardStep === 1) body = this._renderStep1();
    else if (this._wizardStep === 2) body = this._renderStep2();
    else if (this._wizardStep === 3) body = this._renderStep3();

    wiz.innerHTML = `
      <div class="wiz-header">
        <h2>${t.h}</h2>
        <p>${t.p}</p>
        <div class="steps">${stepDots}</div>
      </div>
      <div class="wiz-body">${body}</div>`;

    this._attachWizardListeners();
  }

  _renderStep1() {
    if (this._wizardLoadError) {
      const isCredentialError = this._wizardLoadErrorType === "no_credentials" || this._wizardLoadErrorType === "invalid_credentials";
      const actionBtn = isCredentialError
        ? `<a href="/config/integrations/integration/finance_dashboard" class="wiz-btn wiz-btn-primary" style="margin-top:12px;display:inline-block;text-decoration:none">Einstellungen öffnen</a>`
        : `<button class="wiz-btn wiz-btn-primary" id="wizRetryLoad" style="margin-top:12px">Erneut versuchen</button>`;
      return `<div class="wait-center">
        <p class="error-msg">${this._wizardLoadError}</p>
        ${actionBtn}
      </div>`;
    }
    if (!this._wizardInstitutions.length) {
      return `<div class="wait-center"><div class="spinner"></div><p>Lade Bankliste...</p></div>`;
    }

    const bankItems = this._wizardInstitutions.map(inst => {
      const selected = this._wizardSelectedBank?.id === inst.id ? " selected" : "";
      const logo = inst.logo
        ? `<img class="bank-logo" src="${inst.logo}" alt="" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">`
        : "";
      const placeholder = `<div class="bank-logo-placeholder" ${inst.logo ? 'style="display:none"' : ""}>${inst.name.charAt(0)}</div>`;
      return `<div class="bank-item${selected}" data-id="${inst.id}" data-name="${inst.name}" data-logo="${inst.logo||""}" data-bic="${inst.bic||""}">
        ${logo}${placeholder}
        <div><div class="bank-name">${inst.name}</div><div class="bank-bic">${inst.bic||""}</div></div>
      </div>`;
    }).join("");

    return `
      <input class="search-input" id="bankSearch" type="text" placeholder="Bank suchen..." autocomplete="off">
      <div class="bank-count" id="bankCount">${this._wizardInstitutions.length} Banken verfügbar</div>
      <div class="bank-list" id="bankList">${bankItems}</div>
      <div id="wizError" class="error-msg"></div>
      <div class="wiz-actions">
        <button class="wiz-btn wiz-btn-primary" id="wizNext1" ${this._wizardSelectedBank ? "" : "disabled"}>Weiter</button>
      </div>`;
  }

  _renderStep2() {
    return `
      <div class="wait-center">
        <div class="spinner"></div>
        <p style="font-size:15px;font-weight:600;margin-bottom:4px">Warte auf Bankfreigabe...</p>
        <p style="font-size:13px;color:var(--tx2)">Ein neuer Tab wurde geöffnet. Autorisiere dort den Zugriff bei <strong>${this._wizardSelectedBank?.name||"deiner Bank"}</strong>.</p>
        <p style="font-size:12px;color:var(--tx2);margin-top:12px">Dieses Fenster aktualisiert sich automatisch (Timeout: 5 Min).</p>
      </div>
      <div id="wizError" class="error-msg"></div>
      <div class="wiz-actions">
        <button class="wiz-btn" id="wizCancelAuth" style="opacity:.7">Abbrechen</button>
      </div>`;
  }

  _renderStep3() {
    if (!this._wizardAccounts.length) {
      return `<div class="wait-center"><div class="spinner"></div><p>Lade Kontodaten...</p></div>`;
    }

    const users = this._wizardHaUsers || [];

    const accItems = this._wizardAccounts.map(acc => {
      const iban = acc.iban ? `****${acc.iban.slice(-4)}` : "****";
      const bankName = acc.name || "Konto";

      const userChips = users.length
        ? `<div class="acc-users-label">Personen zuweisen:</div>
           <div class="acc-users-chips">${users.map(u =>
             `<span class="acc-user-chip" data-user-id="${u.id}" data-user-name="${u.name}">${u.name}</span>`
           ).join("")}</div>`
        : `<input data-field="person" type="text" placeholder="Person (optional)">`;

      return `<div class="acc-item" data-acc-id="${acc.id}">
        <div class="acc-header">
          <span class="acc-name">${bankName}</span>
          <span class="acc-iban">${iban}</span>
        </div>
        <div class="acc-fields">
          <div class="acc-fields-row">
            <select data-field="type">
              <option value="personal">Persönlich</option>
              <option value="shared">Gemeinsam</option>
            </select>
            <input data-field="custom_name" type="text" placeholder="Anzeigename (optional)">
          </div>
          ${userChips}
        </div>
      </div>`;
    }).join("");

    return `
      ${accItems}
      <div id="wizError" class="error-msg"></div>
      <div class="wiz-actions">
        <button class="wiz-btn wiz-btn-primary" id="wizComplete">Fertig</button>
      </div>`;
  }

  _attachWizardListeners() {
    // Retry button (shown on load error)
    const retryBtn = this.shadowRoot.getElementById("wizRetryLoad");
    if (retryBtn) {
      retryBtn.addEventListener("click", () => {
        this._wizardLoadError = null;
        this._renderWizardStep();
        this._loadInstitutions();
      });
    }

    if (this._wizardStep === 1) {
      // Search filter
      const searchInput = this.shadowRoot.getElementById("bankSearch");
      if (searchInput) {
        searchInput.addEventListener("input", (e) => {
          const q = e.target.value.toLowerCase();
          const items = this.shadowRoot.querySelectorAll(".bank-item");
          let visible = 0;
          items.forEach(item => {
            const name = item.dataset.name.toLowerCase();
            const bic = item.dataset.bic.toLowerCase();
            const show = name.includes(q) || bic.includes(q);
            item.style.display = show ? "" : "none";
            if (show) visible++;
          });
          const countEl = this.shadowRoot.getElementById("bankCount");
          if (countEl) countEl.textContent = `${visible} Banken gefunden`;
        });
        searchInput.focus();
      }

      // Bank selection
      const bankList = this.shadowRoot.getElementById("bankList");
      if (bankList) {
        bankList.addEventListener("click", (e) => {
          const item = e.target.closest(".bank-item");
          if (!item) return;
          this.shadowRoot.querySelectorAll(".bank-item.selected").forEach(el => el.classList.remove("selected"));
          item.classList.add("selected");
          this._wizardSelectedBank = {
            id: item.dataset.id,
            name: item.dataset.name,
            logo: item.dataset.logo,
            bic: item.dataset.bic,
          };
          const btn = this.shadowRoot.getElementById("wizNext1");
          if (btn) btn.disabled = false;
        });
      }

      // Next button
      const nextBtn = this.shadowRoot.getElementById("wizNext1");
      if (nextBtn) {
        nextBtn.addEventListener("click", () => this._startAuthorization());
      }
    }

    if (this._wizardStep === 2) {
      const cancelBtn = this.shadowRoot.getElementById("wizCancelAuth");
      if (cancelBtn) {
        cancelBtn.addEventListener("click", () => {
          if (this._wizardPollTimer) {
            clearInterval(this._wizardPollTimer);
            this._wizardPollTimer = null;
          }
          this._wizardStep = 1;
          this._renderWizardStep();
        });
      }
    }

    if (this._wizardStep === 3) {
      // User chip toggle (multi-select)
      this.shadowRoot.querySelectorAll(".acc-user-chip").forEach(chip => {
        chip.addEventListener("click", () => chip.classList.toggle("selected"));
      });

      const completeBtn = this.shadowRoot.getElementById("wizComplete");
      if (completeBtn) {
        completeBtn.addEventListener("click", () => this._completeSetup());
      }
    }
  }

  async _loadInstitutions() {
    this._wizardLoadError = null;
    this._wizardLoadErrorType = null;
    try {
      const result = await this._hass.callApi("GET", "finance_dashboard/setup/institutions");
      if (result.error) {
        const err = new Error(result.error);
        err.errorType = result.error_type || "unknown";
        throw err;
      }
      this._wizardInstitutions = (result.institutions || []).sort((a,b) => a.name.localeCompare(b.name));
    } catch (e) {
      console.error("Failed to load institutions:", e);
      // Extract error_type — may be on the error object (200-with-error)
      // or embedded in the message string (non-200 response body)
      let errorType = e.errorType || "unknown";
      if (errorType === "unknown" && e.message) {
        try {
          const bodyMatch = e.message.match(/\{.*\}/s);
          if (bodyMatch) {
            const parsed = JSON.parse(bodyMatch[0]);
            if (parsed.error_type) errorType = parsed.error_type;
          }
        } catch (_) { /* not JSON, keep unknown */ }
      }
      this._wizardLoadErrorType = errorType;
      if (errorType === "no_credentials") {
        this._wizardLoadError = "Keine API-Zugangsdaten hinterlegt. Bitte richte die Integration zuerst in den Einstellungen ein.";
      } else if (errorType === "invalid_credentials") {
        this._wizardLoadError = "Die API-Zugangsdaten wurden abgelehnt. Bitte prüfe Application ID und Private Key in den Integrationseinstellungen.";
      } else if (errorType === "timeout") {
        this._wizardLoadError = "Die Enable Banking API antwortet nicht. Bitte versuche es in einigen Minuten erneut.";
      } else {
        this._wizardLoadError = "Fehler beim Laden der Bankliste. Bitte versuche es erneut oder prüfe die Integrationseinstellungen.";
      }
    }
    this._renderWizardStep();
  }

  async _loadHaUsers() {
    try {
      const result = await this._hass.callApi("GET", "finance_dashboard/setup/users");
      this._wizardHaUsers = result.users || [];
    } catch (e) {
      console.warn("Failed to load HA users:", e);
      this._wizardHaUsers = [];
    }
  }

  async _startAuthorization() {
    if (!this._wizardSelectedBank) return;

    const errEl = this.shadowRoot.getElementById("wizError");

    try {
      const result = await this._hass.callApi("POST", "finance_dashboard/setup/authorize", {
        institution_name: this._wizardSelectedBank.name,
        institution_id: this._wizardSelectedBank.id,
        institution_logo: this._wizardSelectedBank.logo,
      });

      if (result.auth_url) {
        // Open bank auth in new tab
        window.open(result.auth_url, "_blank");

        // Advance to step 2
        this._wizardStep = 2;
        this._renderWizardStep();

        // Start polling for auth completion
        this._startAuthPolling();
      } else {
        if (errEl) errEl.textContent = result.error || "Autorisierung fehlgeschlagen.";
      }
    } catch (e) {
      console.error("Authorization failed:", e);
      let msg = "Verbindungsfehler bei der Bankfreigabe.";
      // Try to extract error detail from response body
      if (e.message) {
        try {
          const bodyMatch = e.message.match(/\{.*\}/s);
          if (bodyMatch) {
            const parsed = JSON.parse(bodyMatch[0]);
            if (parsed.error) msg = parsed.error;
          }
        } catch (_) { /* not JSON */ }
      }
      if (errEl) errEl.textContent = msg;
    }
  }

  _startAuthPolling() {
    if (this._wizardPollTimer) clearInterval(this._wizardPollTimer);

    const POLL_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes
    const pollStart = Date.now();

    this._wizardPollTimer = setInterval(async () => {
      // Timeout — stop polling after 5 minutes
      if (Date.now() - pollStart > POLL_TIMEOUT_MS) {
        clearInterval(this._wizardPollTimer);
        this._wizardPollTimer = null;
        this._wizardStep = 1;
        this._wizardLoadError = "Zeitüberschreitung bei der Bankfreigabe. Die Autorisierung wurde nicht rechtzeitig abgeschlossen.";
        this._wizardLoadErrorType = "timeout";
        this._renderWizardStep();
        return;
      }

      try {
        const status = await this._hass.callApi("GET", "finance_dashboard/setup/status");
        if (status.pending_auth_code && status.pending_accounts?.length) {
          clearInterval(this._wizardPollTimer);
          this._wizardPollTimer = null;
          this._wizardAccounts = status.pending_accounts;
          this._wizardStep = 3;
          this._renderWizardStep();
        }
      } catch (e) {
        // Continue polling on error
      }
    }, 2000);
  }

  async _completeSetup() {
    const completeBtn = this.shadowRoot.getElementById("wizComplete");
    if (completeBtn) {
      completeBtn.disabled = true;
      completeBtn.textContent = "Wird eingerichtet...";
    }

    // Collect account assignments
    const accounts = [];
    const accItems = this.shadowRoot.querySelectorAll(".acc-item");
    accItems.forEach(item => {
      const id = item.dataset.accId;
      const type = item.querySelector('[data-field="type"]')?.value || "personal";
      const customName = item.querySelector('[data-field="custom_name"]')?.value || "";

      // Collect selected HA users (chips with .selected class)
      const selectedChips = item.querySelectorAll(".acc-user-chip.selected");
      const haUsers = Array.from(selectedChips).map(chip => ({
        id: chip.dataset.userId,
        name: chip.dataset.userName,
      }));

      // Fallback: free-text person field (when no HA users available)
      const person = item.querySelector('[data-field="person"]')?.value || "";

      accounts.push({ id, type, custom_name: customName, ha_users: haUsers, person });
    });

    try {
      const result = await this._hass.callApi("POST", "finance_dashboard/setup/complete", { accounts });
      if (result.success) {
        this._hideSetupWizard();
        // Poll until the entry reload completes and configured=true
        await this._waitForConfigured();
        this._refresh();
      } else {
        const errEl = this.shadowRoot.getElementById("wizError");
        if (errEl) errEl.textContent = result.error || "Einrichtung fehlgeschlagen.";
        if (completeBtn) {
          completeBtn.disabled = false;
          completeBtn.textContent = "Fertig";
        }
      }
    } catch (e) {
      const errEl = this.shadowRoot.getElementById("wizError");
      if (errEl) errEl.textContent = "Verbindungsfehler bei der Einrichtung.";
      if (completeBtn) {
        completeBtn.disabled = false;
        completeBtn.textContent = "Fertig";
      }
    }
  }

  async _waitForConfigured(maxAttempts = 15) {
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise(r => setTimeout(r, 2000));
      try {
        const status = await this._hass.callApi("GET", "finance_dashboard/setup/status");
        if (status.configured) return;
      } catch (_) { /* endpoint may be briefly unavailable during reload */ }
    }
  }

  // ==================== Dashboard Drawing ====================

  _draw(el, balances, txnData, summary) {
    const eur = (v) => new Intl.NumberFormat("de-DE",{style:"currency",currency:"EUR"}).format(v);
    const cats = summary?.categories || {};
    const totalExp = summary?.total_expenses || 0;
    const totalInc = summary?.total_income || 0;

    // Calculate real bank balance from account balances (not summary income-expenses)
    let bankBalance = 0;
    let accountCount = 0;
    if (balances && typeof balances === "object") {
      for (const acc of Object.values(balances)) {
        const bals = acc.balances || [];
        // Prefer "expected" balance, fall back to first available
        const balEntry = bals.find(b => b.balanceType === "expected")
          || bals.find(b => b.balanceType === "closingBooked")
          || bals[0];
        if (balEntry) {
          const amt = parseFloat(balEntry.balanceAmount?.amount ?? balEntry.amount ?? 0);
          if (!isNaN(amt)) { bankBalance += amt; accountCount++; }
        }
      }
    }
    // Fallback to summary balance if no bank balance data available
    const balance = accountCount > 0 ? bankBalance : (summary?.balance || 0);
    const balanceSource = accountCount > 0
      ? `${accountCount} ${accountCount === 1 ? "Konto" : "Konten"}`
      : "Aktueller Monat";

    // Store balances for settings overlay
    this._lastBalances = balances;

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

    // Fixed vs variable
    const fixedCats = ["housing","loans","utilities","insurance"];
    const fixedTotal = sorted.filter(([c])=>fixedCats.includes(c)).reduce((s,[,a])=>s+Math.abs(a),0);
    const varTotal = totalExp - fixedTotal;
    const fixPct = totalExp > 0 ? Math.round(fixedTotal/totalExp*100) : 0;

    el.innerHTML = `
      <div class="stats">
        <div class="stat"><div class="stat-l">Gesamtsaldo</div>
          <div class="stat-v ${balance >= 0 ? "pos" : "neg"}">${eur(balance)}</div>
          <div class="stat-d neu">${balanceSource}</div></div>
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

      ${this._renderTransactionList(txnData, summary)}
    `;
    el.classList.remove("loading");

    // Bind chain badge click handlers
    el.querySelectorAll(".txn-chain-badge").forEach(badge => {
      badge.addEventListener("click", () => {
        this._showChainDetail(badge.dataset.chainId);
      });
    });

    // Bind show-more button
    const showMoreBtn = el.querySelector(".txn-show-more button");
    if (showMoreBtn) {
      showMoreBtn.addEventListener("click", () => {
        this._txnLimit = (this._txnLimit || 10) + 20;
        this._refresh();
      });
    }
  }

  _renderTransactionList(txnData, summary) {
    const eur = (v) => new Intl.NumberFormat("de-DE",{style:"currency",currency:"EUR"}).format(v);
    const txns = txnData?.transactions || [];
    if (!txns.length) return "";

    const limit = this._txnLimit || 10;
    const visible = txns.slice(0, limit);
    const excluded = summary?.excluded_transfers || {};

    // Excluded transfers info banner
    let excludedBanner = "";
    if (excluded.chain_count > 0) {
      excludedBanner = `<div style="padding:8px 18px;font-size:11px;color:var(--tx2);background:rgba(78,204,163,0.06);border-bottom:1px solid var(--bd)">
        &#x1f517; ${excluded.chain_count} Transfer-Kette${excluded.chain_count > 1 ? "n" : ""} erkannt
        &mdash; ${eur(excluded.excluded_amount)} ausgeblendet (${excluded.excluded_txn_count} Zwischenbuchungen)
      </div>`;
    }

    const rows = visible.map(txn => {
      const amt = parseFloat(txn.amount || 0);
      const cls = txn.transfer_role === "intermediate" ? "txn-row intermediate" : "txn-row";

      // Chain badge
      let badge = "";
      if (txn.transfer_chain_id) {
        const conf = txn.transfer_confirmed;
        const badgeCls = conf === true ? "txn-chain-badge" :
                         conf === false ? "" : "txn-chain-badge unconfirmed";
        if (conf !== false) {
          const roleLabel = txn.transfer_role === "source" ? "Quelle" :
                            txn.transfer_role === "intermediate" ? "Durchlauf" :
                            txn.transfer_role === "destination" ? "Ziel" : "";
          badge = `<span class="${badgeCls}" data-chain-id="${txn.transfer_chain_id}"
            title="Transfer-Kette: ${roleLabel}">&#x1f517; ${roleLabel}</span>`;
        }
      }

      // Refund badge
      if (txn.refund_pair_id) {
        const refLabel = txn.refund_role === "refund" ? "Erstattung" : "Erstattet";
        badge += `<span class="txn-refund-badge" title="${refLabel}">&#x21a9; ${refLabel}</span>`;
      }

      return `<div class="${cls}">
        <span class="txn-date">${txn.date || ""}</span>
        <span class="txn-desc">
          ${txn.creditor || txn.description || "—"}
          ${txn.account_name ? `<span class="txn-acct">${txn.account_name}</span>` : ""}
          ${badge}
        </span>
        <span class="txn-amt ${amt >= 0 ? "pos" : "neg"}">${eur(amt)}</span>
      </div>`;
    }).join("");

    const showMore = txns.length > limit
      ? `<div class="txn-show-more"><button>Weitere laden (${txns.length - limit} verbleibend)</button></div>`
      : "";

    return `<div class="card grid-full">
      <div class="card-h">Transaktionen</div>
      ${excludedBanner}
      <div class="txn-list">${rows}</div>
      ${showMore}
    </div>`;
  }

  _showChainDetail(chainId) {
    if (!chainId) return;
    const chain = (this._chainData || []).find(c => c.chain_id === chainId);
    if (!chain) return;

    const eur = (v) => new Intl.NumberFormat("de-DE",{style:"currency",currency:"EUR"}).format(v);
    const container = this.shadowRoot.getElementById("overlay-container");
    if (!container) return;

    const steps = (chain.transactions || []).map(txn => {
      const roleCls = txn.role || "source";
      const roleLabel = txn.role === "source" ? "Quelle" :
                        txn.role === "intermediate" ? "Durchlauf" :
                        txn.role === "destination" ? "Ziel" : "";
      return `<div class="chain-step">
        <span class="chain-role ${roleCls}">${roleLabel}</span>
        <span style="flex:1">${txn.account_name || ""} &mdash; ${txn.creditor || txn.description || ""}</span>
        <span class="${parseFloat(txn.amount) >= 0 ? "pos" : "neg"}">${eur(txn.amount)}</span>
      </div>`;
    });

    // Add arrows between steps
    const flow = steps.reduce((acc, step, i) => {
      acc.push(step);
      if (i < steps.length - 1) acc.push(`<div class="chain-arrow">&#x2193;</div>`);
      return acc;
    }, []).join("");

    const confPct = Math.round((chain.confidence || 0) * 100);
    const isConfirmed = chain.confirmed;

    container.innerHTML = `<div class="chain-overlay" id="chain-overlay">
      <div class="chain-detail">
        <div class="chain-title">Transfer-Kette</div>
        <div class="chain-flow">${flow}</div>
        <div class="chain-confidence">Konfidenz: ${confPct}%</div>
        ${isConfirmed === null || isConfirmed === undefined ? `
          <div class="chain-actions">
            <button class="btn btn-p" id="chain-confirm">Korrekt</button>
            <button class="btn" id="chain-reject">Keine Kette</button>
          </div>
        ` : `<div style="font-size:12px;color:var(--tx2)">${isConfirmed ? "Von dir bestaetigt" : "Von dir abgelehnt"}</div>`}
        <div style="margin-top:14px;text-align:right">
          <button class="btn" id="chain-close">Schliessen</button>
        </div>
      </div>
    </div>`;

    container.querySelector("#chain-close").addEventListener("click", () => {
      container.innerHTML = "";
    });
    container.querySelector("#chain-overlay").addEventListener("click", (e) => {
      if (e.target.id === "chain-overlay") container.innerHTML = "";
    });

    const confirmBtn = container.querySelector("#chain-confirm");
    const rejectBtn = container.querySelector("#chain-reject");
    if (confirmBtn) {
      confirmBtn.addEventListener("click", async () => {
        await this._hass.callApi("POST", "finance_dashboard/transfer_chains",
          { chain_id: chainId, confirmed: true });
        container.innerHTML = "";
        this._refresh();
      });
    }
    if (rejectBtn) {
      rejectBtn.addEventListener("click", async () => {
        await this._hass.callApi("POST", "finance_dashboard/transfer_chains",
          { chain_id: chainId, confirmed: false });
        container.innerHTML = "";
        this._refresh();
      });
    }
  }

  // ==================== Settings / Manage Overlay ====================

  async _showManageOverlay() {
    const container = this.shadowRoot.getElementById("overlay-container");
    if (!container || container.querySelector(".overlay")) return;

    // Load current accounts and HA users
    this._manageAccounts = [];
    this._manageHaUsers = [];
    this._manageSaving = false;

    container.innerHTML = `<div class="overlay"><div class="wizard" id="manageWiz">
      <div class="wiz-header"><h2>Konten verwalten</h2>
        <p>Bankkonten umbenennen, Personen zuordnen oder neue Bank hinzufugen.</p></div>
      <div class="wiz-body"><div class="wait-center"><div class="spinner"></div><p>Lade Konten...</p></div></div>
    </div></div>`;

    // Close on backdrop click
    container.querySelector(".overlay").addEventListener("click", (e) => {
      if (e.target === e.currentTarget) this._hideManageOverlay();
    });

    try {
      const [statusResp, usersResp] = await Promise.all([
        this._hass.callApi("GET", "finance_dashboard/setup/status"),
        this._hass.callApi("GET", "finance_dashboard/setup/users"),
      ]);
      this._manageAccounts = statusResp.accounts || [];
      this._manageHaUsers = usersResp.users || [];
      this._renderManageContent();
    } catch (e) {
      const body = container.querySelector(".wiz-body");
      if (body) body.innerHTML = `<div class="error-msg">Fehler beim Laden der Konten.</div>
        <div class="wiz-actions"><button class="wiz-btn wiz-btn-secondary" id="manageClose">Schliessen</button></div>`;
      container.querySelector("#manageClose")?.addEventListener("click", () => this._hideManageOverlay());
    }
  }

  _hideManageOverlay() {
    const container = this.shadowRoot.getElementById("overlay-container");
    if (container) container.innerHTML = "";
  }

  _renderManageContent() {
    const wiz = this.shadowRoot.getElementById("manageWiz");
    if (!wiz) return;

    const accounts = this._manageAccounts;
    const users = this._manageHaUsers;

    const accountsHtml = accounts.map((acc, i) => {
      const logoHtml = acc.logo
        ? `<img src="${acc.logo}" alt="">`
        : `<div class="bank-logo-placeholder">${(acc.institution || "?")[0]}</div>`;

      const userChips = users.map(u => {
        const sel = (acc.ha_users || []).includes(u.id) ? "selected" : "";
        return `<span class="acc-user-chip ${sel}" data-acc="${i}" data-uid="${u.id}">${u.name}</span>`;
      }).join("");

      return `<div class="manage-acc" data-idx="${i}">
        <div class="manage-acc-hdr">
          <div class="manage-acc-bank">${logoHtml}<span>${acc.institution || ""}</span></div>
          <div class="manage-acc-iban">${acc.iban_masked || acc.iban || ""}</div>
        </div>
        <div class="manage-fields">
          <div class="manage-field-row">
            <label>Name</label>
            <input type="text" value="${acc.custom_name || acc.name || ""}" data-field="custom_name" data-idx="${i}" placeholder="Kontoname">
          </div>
          <div class="manage-field-row">
            <label>Typ</label>
            <select data-field="type" data-idx="${i}">
              <option value="personal" ${acc.type === "personal" ? "selected" : ""}>Persoenlich</option>
              <option value="shared" ${acc.type === "shared" ? "selected" : ""}>Gemeinsam</option>
            </select>
          </div>
          <div>
            <div class="acc-users-label">Personen</div>
            <div class="acc-users-chips">${userChips}</div>
          </div>
        </div>
      </div>`;
    }).join("");

    wiz.innerHTML = `
      <div class="wiz-header"><h2>Konten verwalten</h2>
        <p>Bankkonten umbenennen, Personen zuordnen oder neue Bank hinzufugen.</p></div>
      <div class="wiz-body">
        <div class="manage-list">${accountsHtml || '<div style="text-align:center;color:var(--tx2);padding:20px">Noch keine Konten verbunden.</div>'}</div>
        <button class="manage-add-btn" id="manageAddBank">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Neue Bank verbinden
        </button>
        <div class="wiz-actions">
          <button class="wiz-btn wiz-btn-secondary" id="manageClose">Abbrechen</button>
          <button class="wiz-btn wiz-btn-primary" id="manageSave">Speichern</button>
        </div>
      </div>`;

    // Event listeners
    wiz.querySelector("#manageClose").addEventListener("click", () => this._hideManageOverlay());
    wiz.querySelector("#manageSave").addEventListener("click", () => this._saveManageChanges());
    wiz.querySelector("#manageAddBank").addEventListener("click", () => {
      this._hideManageOverlay();
      this._showSetupWizard();
    });

    // Input change handlers
    wiz.querySelectorAll("input[data-field], select[data-field]").forEach(el => {
      el.addEventListener("change", () => {
        const idx = parseInt(el.dataset.idx);
        const field = el.dataset.field;
        if (this._manageAccounts[idx]) {
          this._manageAccounts[idx][field] = el.value;
        }
      });
    });

    // User chip toggle
    wiz.querySelectorAll(".acc-user-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        const idx = parseInt(chip.dataset.acc);
        const uid = chip.dataset.uid;
        const acc = this._manageAccounts[idx];
        if (!acc) return;
        if (!acc.ha_users) acc.ha_users = [];
        const uidIdx = acc.ha_users.indexOf(uid);
        if (uidIdx >= 0) {
          acc.ha_users.splice(uidIdx, 1);
          chip.classList.remove("selected");
        } else {
          acc.ha_users.push(uid);
          chip.classList.add("selected");
        }
      });
    });
  }

  async _saveManageChanges() {
    if (this._manageSaving) return;
    this._manageSaving = true;

    const saveBtn = this.shadowRoot.querySelector("#manageSave");
    if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = "Speichern..."; }

    try {
      await this._hass.callApi("POST", "finance_dashboard/setup/update_accounts", {
        accounts: this._manageAccounts.map(acc => ({
          id: acc.id,
          custom_name: acc.custom_name || acc.name || "",
          type: acc.type || "personal",
          ha_users: acc.ha_users || [],
        })),
      });
      this._hideManageOverlay();
      this._refresh();
    } catch (e) {
      if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = "Speichern"; }
      const body = this.shadowRoot.querySelector(".wiz-body");
      const existing = body?.querySelector(".error-msg");
      if (existing) existing.remove();
      const err = document.createElement("div");
      err.className = "error-msg";
      err.textContent = "Fehler beim Speichern. Bitte erneut versuchen.";
      body?.querySelector(".wiz-actions")?.before(err);
    } finally {
      this._manageSaving = false;
    }
  }

}

if (!customElements.get("finance-dashboard-panel")) {
  customElements.define("finance-dashboard-panel", FinanceDashboardPanel);
}

export default FinanceDashboardPanel;
