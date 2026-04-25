/**
 * fd-setup-wizard — Modal overlay for inline bank account connection.
 *
 * Steps:
 *   1. Institution selection (search + select from Enable Banking list)
 *   2. Authorization (open bank auth URL, poll for callback)
 *   3. Account assignment (name, type, person per account)
 *   4. Success confirmation
 *
 * Uses existing API endpoints:
 *   GET  setup/status
 *   GET  setup/institutions
 *   POST setup/authorize
 *   GET  setup/status (poll for pending_accounts after callback)
 *   POST setup/complete
 *   GET  setup/users
 *
 * Events dispatched:
 *   fd-setup-complete — Wizard finished successfully, data provider should refresh
 *   fd-setup-closed   — Wizard closed (cancel or success)
 */

// DOMAIN is declared by fd-data-provider.js (loaded first, shared global scope)
const POLL_INTERVAL_MS = 2000;
const POLL_MAX_MS = 300000; // 5 minutes

class FdSetupWizard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._step = 1; // 1=institutions, 2=authorize, 3=accounts, 4=done
    this._institutions = [];
    this._filteredInstitutions = [];
    this._selectedInstitution = null;
    this._authUrl = null;
    this._pendingAccounts = [];
    this._pollTimer = null;
    this._error = null;
    this._loading = false;
    this._boundTrapFocus = this._trapFocus.bind(this);
    this._boundEsc = this._handleEsc.bind(this);
  }

  set hass(hass) {
    this._hass = hass;
  }

  connectedCallback() {
    this._render();
    this._loadInstitutions();
    document.addEventListener("keydown", this._boundTrapFocus);
    document.addEventListener("keydown", this._boundEsc);
    // Move focus into modal after render
    requestAnimationFrame(() => {
      const first = this._getFocusable()[0];
      if (first) first.focus();
    });
  }

  disconnectedCallback() {
    this._stopPolling();
    document.removeEventListener("keydown", this._boundTrapFocus);
    document.removeEventListener("keydown", this._boundEsc);
  }

  _getFocusable() {
    const selectors = "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])";
    return Array.from(this.shadowRoot.querySelectorAll(selectors)).filter(
      (el) => !el.disabled && !el.closest("[hidden]")
    );
  }

  _trapFocus(e) {
    if (e.key !== "Tab") return;
    const focusable = this._getFocusable();
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    // Determine what is currently focused inside the shadow root
    const active = this.shadowRoot.activeElement;
    if (e.shiftKey) {
      if (active === first || !active) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (active === last || !active) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  _handleEsc(e) {
    if (e.key === "Escape") {
      e.preventDefault();
      this.close();
    }
  }

  close() {
    this._stopPolling();
    this.dispatchEvent(new CustomEvent("fd-setup-closed", {
      bubbles: true,
      composed: true,
    }));
    this.remove();
  }

  async _loadInstitutions() {
    if (!this._hass) return;
    this._loading = true;
    this._error = null;
    this._renderContent();
    try {
      const result = await this._hass.callApi("GET", `${DOMAIN}/setup/institutions`);
      if (result.error) {
        this._error = result.error;
      } else {
        this._institutions = result.institutions || [];
        this._filteredInstitutions = this._institutions;
      }
    } catch (e) {
      this._error = "Banken konnten nicht geladen werden";
    }
    this._loading = false;
    this._renderContent();
  }

  async _loadUsers() {
    // Reserved for future HA user picker (currently person is free-text)
  }

  async _authorize(institution) {
    this._selectedInstitution = institution;
    this._loading = true;
    this._error = null;
    this._step = 2;
    this._renderContent();

    try {
      const result = await this._hass.callApi("POST", `${DOMAIN}/setup/authorize`, {
        institution_name: institution.name,
        institution_id: institution.id || "",
        institution_logo: institution.logo || "",
      });
      if (result.error) {
        this._error = result.error;
        this._loading = false;
        this._renderContent();
        return;
      }
      this._authUrl = result.auth_url;
      this._loading = false;
      this._renderContent();
      // Open auth URL in new tab (only https/http)
      if (/^https?:\/\//.test(this._authUrl)) {
        window.open(this._authUrl, "_blank");
      }
      // Start polling for callback completion
      this._startPolling();
    } catch (e) {
      this._error = "Autorisierung fehlgeschlagen";
      this._loading = false;
      this._renderContent();
    }
  }

  _startPolling() {
    const startTime = Date.now();
    this._pollTimer = setInterval(async () => {
      if (Date.now() - startTime > POLL_MAX_MS) {
        this._stopPolling();
        this._error = "Zeitlimit erreicht. Bitte erneut versuchen.";
        this._renderContent();
        return;
      }
      try {
        const status = await this._hass.callApi("GET", `${DOMAIN}/setup/status`);
        // Backend reported a setup error during the OAuth callback —
        // stop polling immediately and show it to the user instead of
        // waiting for the 5-minute timeout.
        if (status.setup_error) {
          this._stopPolling();
          this._error = status.setup_error;
          this._step = 1;
          this._renderContent();
          return;
        }
        if (status.pending_accounts && status.pending_accounts.length > 0) {
          this._stopPolling();
          this._pendingAccounts = status.pending_accounts.map((acc) => ({
            ...acc,
            custom_name: acc.name || "",
            type: "personal",
            person: "",
            ha_users: [],
          }));
          await this._loadUsers();
          this._step = 3;
          this._renderContent();
        }
      } catch (e) {
        // Silently retry
      }
    }, POLL_INTERVAL_MS);
  }

  _stopPolling() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  }

  async _completeSetup() {
    this._loading = true;
    this._error = null;
    this._renderContent();

    const accounts = this._pendingAccounts.map((acc) => ({
      id: acc.id,
      custom_name: acc.custom_name,
      type: acc.type,
      person: acc.person,
      ha_users: acc.ha_users,
    }));

    try {
      const result = await this._hass.callApi("POST", `${DOMAIN}/setup/complete`, {
        accounts,
      });
      if (result.error) {
        this._error = result.error;
        this._loading = false;
        this._renderContent();
        return;
      }
      this._loading = false;
      this._step = 4;
      this._renderContent();
      this.dispatchEvent(new CustomEvent("fd-setup-complete", {
        bubbles: true,
        composed: true,
      }));
    } catch (e) {
      this._error = "Setup konnte nicht abgeschlossen werden";
      this._loading = false;
      this._renderContent();
    }
  }

  _filterInstitutions(query) {
    const q = query.toLowerCase().trim();
    if (!q) {
      this._filteredInstitutions = this._institutions;
    } else {
      this._filteredInstitutions = this._institutions.filter(
        (i) => i.name.toLowerCase().includes(q)
      );
    }
    // Update only the list container — don't replace the input (avoids cursor jump)
    const list = this.shadowRoot.querySelector(".institution-list");
    if (list) {
      list.innerHTML = this._renderInstitutionList();
      this._bindInstitutionClicks();
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
<style>
:host {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}
.backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0,0,0,0.7);
  backdrop-filter: blur(4px);
}
.modal {
  position: relative;
  width: 90%;
  max-width: 520px;
  max-height: 80vh;
  background: var(--card-background-color, #12121a);
  border-radius: 16px;
  border: 1px solid rgba(255,255,255,0.08);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0,0,0,0.5);
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.modal-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--primary-text-color, #e0e0e0);
}
.close-btn {
  background: none;
  border: none;
  color: var(--secondary-text-color, #9898a8);
  font-size: 22px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 8px;
}
.close-btn:hover { background: rgba(255,255,255,0.06); }
.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
.steps {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}
.step-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(255,255,255,0.15);
}
.step-dot.active { background: var(--accent-color, #4ecca3); }
.step-dot.done { background: var(--accent-color, #4ecca3); opacity: 0.5; }
.search-input {
  width: 100%;
  padding: 12px 16px;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.04);
  color: var(--primary-text-color, #e0e0e0);
  font-size: 14px;
  font-family: inherit;
  box-sizing: border-box;
  outline: none;
  margin-bottom: 16px;
}
.search-input:focus { border-color: var(--accent-color, #4ecca3); }
.search-input::placeholder { color: var(--secondary-text-color, #9898a8); }
.institution-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 320px;
  overflow-y: auto;
}
.institution-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  cursor: pointer;
  border: 1px solid transparent;
}
.institution-item:hover,
.institution-item:focus {
  background: rgba(255,255,255,0.04);
  border-color: rgba(255,255,255,0.08);
  outline: none;
}
.institution-item[aria-selected="true"] {
  background: rgba(78,204,163,0.1);
  border-color: var(--accent-color, #4ecca3);
}
.institution-item .selected-mark {
  margin-left: auto;
  color: var(--accent-color, #4ecca3);
  font-size: 14px;
}
.institution-item img {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  object-fit: contain;
  background: #fff;
}
.institution-item .name {
  font-size: 14px;
  font-weight: 500;
}
.error-msg {
  padding: 12px 16px;
  border-radius: 10px;
  background: rgba(231,76,60,0.1);
  border: 1px solid rgba(231,76,60,0.3);
  color: var(--error-color, #e74c3c);
  font-size: 13px;
  margin-bottom: 16px;
}
.loading-spinner {
  text-align: center;
  padding: 40px;
  color: var(--secondary-text-color, #9898a8);
}
.auth-card {
  text-align: center;
  padding: 20px 0;
}
.auth-card p {
  color: var(--secondary-text-color, #9898a8);
  line-height: 1.5;
  margin: 0 0 20px;
}
.auth-card .waiting {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--accent-color, #4ecca3);
  font-size: 13px;
  margin-top: 20px;
}
.btn-primary {
  display: inline-block;
  padding: 12px 24px;
  border-radius: 10px;
  background: var(--accent-color, #4ecca3);
  color: var(--primary-background-color, #0a0a0f);
  font-size: 14px;
  font-weight: 700;
  border: none;
  cursor: pointer;
  font-family: inherit;
  text-decoration: none;
}
.btn-primary:hover { opacity: 0.9; }
.btn-primary:disabled { opacity: 0.5; cursor: default; }
.btn-secondary {
  padding: 10px 20px;
  border-radius: 10px;
  background: transparent;
  border: 1px solid rgba(255,255,255,0.1);
  color: var(--primary-text-color, #e0e0e0);
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
}
.btn-secondary:hover { background: rgba(255,255,255,0.04); }
.account-card {
  padding: 16px;
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.02);
  margin-bottom: 12px;
}
.account-card .acc-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.account-card .acc-header img {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  object-fit: contain;
  background: #fff;
}
.account-card .acc-header .acc-name {
  font-weight: 600;
  font-size: 14px;
}
.account-card .acc-header .acc-iban {
  font-size: 12px;
  color: var(--secondary-text-color, #9898a8);
}
.form-row {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}
.form-row label {
  font-size: 12px;
  color: var(--secondary-text-color, #9898a8);
  display: block;
  margin-bottom: 4px;
}
.form-row input, .form-row select {
  width: 100%;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.04);
  color: var(--primary-text-color, #e0e0e0);
  font-size: 13px;
  font-family: inherit;
  box-sizing: border-box;
}
.form-row input:focus, .form-row select:focus {
  outline: none;
  border-color: var(--accent-color, #4ecca3);
}
.form-field { flex: 1; }
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}
.success-card {
  text-align: center;
  padding: 30px 0;
}
.success-card .icon { font-size: 48px; margin-bottom: 16px; }
.success-card h3 {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 700;
}
.success-card p {
  color: var(--secondary-text-color, #9898a8);
  margin: 0 0 24px;
}
</style>
<div class="backdrop"></div>
<div class="modal" role="dialog" aria-modal="true" aria-labelledby="wizard-title">
  <div class="modal-header">
    <h2 id="wizard-title">Bankkonto verbinden</h2>
    <button class="close-btn" id="closeBtn" aria-label="Dialog schließen">&times;</button>
  </div>
  <div class="modal-body" id="body"></div>
</div>`;

    this.shadowRoot.querySelector(".backdrop")
      .addEventListener("click", () => this.close());
    this.shadowRoot.getElementById("closeBtn")
      .addEventListener("click", () => this.close());

    this._renderContent();
  }

  _renderContent() {
    const body = this.shadowRoot.getElementById("body");
    if (!body) return;

    // Step indicators
    const stepsHtml = `<div class="steps">
      ${[1, 2, 3, 4].map((s) =>
        `<div class="step-dot ${s === this._step ? "active" : s < this._step ? "done" : ""}"></div>`
      ).join("")}
    </div>`;

    const errorHtml = this._error
      ? `<div class="error-msg">${this._esc(this._error)}</div>`
      : "";

    if (this._step === 1) {
      body.innerHTML = `${stepsHtml}${errorHtml}${this._renderStep1()}`;
      this._bindStep1();
    } else if (this._step === 2) {
      body.innerHTML = `${stepsHtml}${errorHtml}${this._renderStep2()}`;
    } else if (this._step === 3) {
      body.innerHTML = `${stepsHtml}${errorHtml}${this._renderStep3()}`;
      this._bindStep3();
    } else if (this._step === 4) {
      body.innerHTML = `${stepsHtml}${this._renderStep4()}`;
      this._bindStep4();
    }

    // Keep focus inside dialog after re-render
    requestAnimationFrame(() => {
      const active = this.shadowRoot.activeElement;
      if (!active || active === this.shadowRoot) {
        const first = this._getFocusable()[0];
        if (first) first.focus();
      }
    });
  }

  _renderInstitutionList() {
    const selected = this._selectedInstitution;
    const items = this._filteredInstitutions.map((inst, idx) => {
      const isSel = selected && selected.name === inst.name;
      return `
      <div class="institution-item"
        role="option"
        aria-selected="${isSel ? "true" : "false"}"
        tabindex="${isSel ? "0" : "-1"}"
        data-idx="${idx}"
        data-name="${this._esc(inst.name)}"
        data-id="${this._esc(inst.id || "")}"
        data-logo="${this._esc(inst.logo || "")}">
        ${inst.logo ? `<img src="${this._esc(inst.logo)}" alt="">` : `<div style="width:32px;height:32px;border-radius:6px;background:#333;"></div>`}
        <span class="name">${this._esc(inst.name)}</span>
        ${isSel ? `<span class="selected-mark" aria-hidden="true">&#x2713;</span>` : ""}
      </div>
    `;
    }).join("");
    return items || '<div style="padding:20px;text-align:center;color:var(--secondary-text-color);">Keine Banken gefunden</div>';
  }

  _bindInstitutionClicks() {
    this.shadowRoot.querySelectorAll(".institution-item").forEach((el) => {
      el.addEventListener("click", () => {
        this._authorize({
          name: el.dataset.name,
          id: el.dataset.id,
          logo: el.dataset.logo,
        });
      });
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          this._authorize({
            name: el.dataset.name,
            id: el.dataset.id,
            logo: el.dataset.logo,
          });
        } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          const items = Array.from(this.shadowRoot.querySelectorAll(".institution-item"));
          const curr = parseInt(el.dataset.idx);
          const next = e.key === "ArrowDown" ? curr + 1 : curr - 1;
          if (next >= 0 && next < items.length) {
            items[next].focus();
          }
        }
      });
    });
  }

  _renderStep1() {
    if (this._loading) {
      return `<div class="loading-spinner">Banken werden geladen\u2026</div>`;
    }
    return `
      <input type="text" class="search-input" id="searchInput" placeholder="Bank suchen\u2026" autocomplete="off" aria-label="Bank suchen">
      <div class="institution-list" role="listbox" aria-label="Bank ausw\u00e4hlen">${this._renderInstitutionList()}</div>
    `;
  }

  _bindStep1() {
    const input = this.shadowRoot.getElementById("searchInput");
    if (input) {
      input.addEventListener("input", (e) => this._filterInstitutions(e.target.value));
      input.addEventListener("keydown", (e) => {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          const first = this.shadowRoot.querySelector(".institution-item");
          if (first) first.focus();
        }
      });
      input.focus();
    }
    this._bindInstitutionClicks();
  }

  _renderStep2() {
    if (this._loading) {
      return `<div class="loading-spinner">Autorisierung wird vorbereitet\u2026</div>`;
    }
    const bankName = this._selectedInstitution ? this._selectedInstitution.name : "Bank";
    return `
      <div class="auth-card">
        <p>Autorisiere den Zugriff bei <strong>${this._esc(bankName)}</strong>.<br>
        Ein neues Fenster wurde ge\u00f6ffnet. Schlie\u00dfe es nach der Best\u00e4tigung.</p>
        ${this._authUrl && /^https?:\/\//.test(this._authUrl) ? `<a href="${this._esc(this._authUrl)}" target="_blank" class="btn-primary">Erneut \u00f6ffnen</a>` : ""}
        <div class="waiting">
          <span>\u23f3</span>
          <span>Warte auf Best\u00e4tigung von der Bank\u2026</span>
        </div>
      </div>
    `;
  }

  _renderStep3() {
    const accountCards = this._pendingAccounts.map((acc, idx) => {
      const iban = acc.iban || "";
      const ibanMasked = iban.length >= 4 ? `****${iban.slice(-4)}` : "****";

      return `
        <div class="account-card" data-idx="${idx}">
          <div class="acc-header">
            ${acc.logo ? `<img src="${this._esc(acc.logo)}" alt="">` : ""}
            <div>
              <div class="acc-name">${this._esc(acc.name || "Konto")}</div>
              <div class="acc-iban">${ibanMasked}</div>
            </div>
          </div>
          <div class="form-row">
            <div class="form-field">
              <label>Anzeigename</label>
              <input type="text" data-field="custom_name" data-idx="${idx}" value="${this._esc(acc.custom_name)}" placeholder="${this._esc(acc.name)}">
            </div>
            <div class="form-field">
              <label>Kontotyp</label>
              <select data-field="type" data-idx="${idx}">
                <option value="personal" ${acc.type === "personal" ? "selected" : ""}>Privat</option>
                <option value="shared" ${acc.type === "shared" ? "selected" : ""}>Gemeinsam</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-field">
              <label>Person</label>
              <input type="text" data-field="person" data-idx="${idx}" value="${this._esc(acc.person)}" placeholder="Name der Person">
            </div>
          </div>
        </div>
      `;
    }).join("");

    return `
      <p style="margin:0 0 16px;color:var(--secondary-text-color);font-size:13px;">
        ${this._pendingAccounts.length} Konto(en) gefunden. Weise sie zu:
      </p>
      ${accountCards}
      <div class="actions">
        <button class="btn-secondary" id="backBtn">Zur\u00fcck</button>
        <button class="btn-primary" id="completeBtn">Verbinden</button>
      </div>
    `;
  }

  _bindStep3() {
    // Input bindings for account fields
    this.shadowRoot.querySelectorAll("[data-field]").forEach((el) => {
      el.addEventListener("change", (e) => {
        const idx = parseInt(e.target.dataset.idx);
        const field = e.target.dataset.field;
        if (this._pendingAccounts[idx]) {
          this._pendingAccounts[idx][field] = e.target.value;
        }
      });
      el.addEventListener("input", (e) => {
        const idx = parseInt(e.target.dataset.idx);
        const field = e.target.dataset.field;
        if (this._pendingAccounts[idx]) {
          this._pendingAccounts[idx][field] = e.target.value;
        }
      });
    });

    const backBtn = this.shadowRoot.getElementById("backBtn");
    if (backBtn) {
      backBtn.addEventListener("click", () => {
        this._step = 1;
        this._error = null;
        this._renderContent();
      });
    }

    const completeBtn = this.shadowRoot.getElementById("completeBtn");
    if (completeBtn) {
      completeBtn.addEventListener("click", () => this._completeSetup());
    }
  }

  _renderStep4() {
    const count = this._pendingAccounts.length;
    return `
      <div class="success-card">
        <div class="icon">&#x2705;</div>
        <h3>Verbindung erfolgreich</h3>
        <p>${count} Konto(en) wurden verbunden. Die Daten werden jetzt geladen.</p>
        <button class="btn-primary" id="doneBtn">Fertig</button>
      </div>
    `;
  }

  _bindStep4() {
    const btn = this.shadowRoot.getElementById("doneBtn");
    if (btn) btn.addEventListener("click", () => this.close());
  }

  _esc(s) {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }
}

customElements.define("fd-setup-wizard", FdSetupWizard);
