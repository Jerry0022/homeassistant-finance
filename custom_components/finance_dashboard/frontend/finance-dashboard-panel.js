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
.acc-fields { display:flex; gap:10px; }
.acc-fields select, .acc-fields input {
  padding:7px 10px; border-radius:8px; border:1px solid var(--bd);
  background:var(--sf); color:var(--tx); font-size:13px; flex:1;
}

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
    <div style="display:flex;gap:6px">
      <button class="btn" id="monthBtn"></button>
      <button class="btn btn-p" id="refreshBtn">Aktualisieren</button>
    </div>
  </div>
  <div id="content" class="loading">Lade Finanzdaten...</div>
  <div id="overlay-container"></div>
</div>`;

    this.shadowRoot.getElementById("refreshBtn")
      .addEventListener("click", () => this._refresh());
  }

  async _refresh() {
    if (!this._hass) return;
    const c = this.shadowRoot.getElementById("content");
    if (!c) return;

    // Check setup status first
    try {
      const status = await this._hass.callApi("GET", "finance_dashboard/setup/status");
      this._configured = status.configured;

      if (!status.configured) {
        c.innerHTML = this._renderEmptyDashboard();
        this._showSetupWizard();
        return;
      }
    } catch (e) {
      // Status endpoint failed — show empty state
      c.innerHTML = `<div class="loading">Lade...</div>`;
      return;
    }

    // Hide wizard if configured
    this._hideSetupWizard();

    // Load dashboard data
    try {
      const [bal, txn, sum] = await Promise.all([
        this._hass.callApi("GET", "finance_dashboard/balances"),
        this._hass.callApi("GET", "finance_dashboard/transactions"),
        this._hass.callApi("GET", "finance_dashboard/summary"),
      ]);
      this._draw(c, bal, txn, sum);
    } catch (e) {
      c.innerHTML = this._renderEmptyDashboard();
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
      <div class="card" style="padding:40px;text-align:center">
        <div style="font-size:36px;margin-bottom:12px">&#127974;</div>
        <div style="font-size:16px;font-weight:600;margin-bottom:6px">Bank verbinden</div>
        <div style="font-size:13px;color:var(--tx2)">Verbinde dein Bankkonto um deine Finanzen zu sehen.</div>
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
    this._wizardPollTimer = null;
    this._wizardLoadError = null;

    container.innerHTML = `<div class="overlay"><div class="wizard" id="wizard"></div></div>`;
    this._renderWizardStep();
    this._loadInstitutions();
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

    const accItems = this._wizardAccounts.map(acc => {
      const iban = acc.iban ? `****${acc.iban.slice(-4)}` : "****";
      const name = acc.name || "Konto";
      return `<div class="acc-item" data-acc-id="${acc.id}">
        <div class="acc-header">
          <span class="acc-name">${name}</span>
          <span class="acc-iban">${iban}</span>
        </div>
        <div class="acc-fields">
          <select data-field="type">
            <option value="personal">Persönlich</option>
            <option value="shared">Gemeinsam</option>
          </select>
          <input data-field="person" type="text" placeholder="Person (optional)">
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
      const errorType = e.errorType || "unknown";
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
      if (errEl) errEl.textContent = "Verbindungsfehler bei der Bankfreigabe.";
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
      const person = item.querySelector('[data-field="person"]')?.value || "";
      accounts.push({ id, type, person });
    });

    try {
      const result = await this._hass.callApi("POST", "finance_dashboard/setup/complete", { accounts });
      if (result.success) {
        this._hideSetupWizard();
        // Wait for entry reload, then refresh
        setTimeout(() => this._refresh(), 2000);
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

  // ==================== Dashboard Drawing ====================

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

    // Fixed vs variable
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

}

if (!customElements.get("finance-dashboard-panel")) {
  customElements.define("finance-dashboard-panel", FinanceDashboardPanel);
}

export default FinanceDashboardPanel;
