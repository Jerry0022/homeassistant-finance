/**
 * fd-header — Title bar with month selector, refresh button, and status chip.
 *
 * Properties:
 *   lastRefresh {string} — ISO timestamp of last data update
 *
 * Events dispatched:
 *   fd-refresh-requested — User clicked refresh button
 */

class FdHeader extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._lastRefresh = null;
    this._refreshing = false;
  }

  set lastRefresh(v) {
    this._lastRefresh = v;
    this._updateTimestamp();
  }

  set refreshing(v) {
    this._refreshing = v;
    const btn = this.shadowRoot.getElementById("refreshBtn");
    if (btn) {
      btn.disabled = v;
      btn.textContent = v ? "Laden\u2026" : "Aktualisieren";
    }
  }

  connectedCallback() {
    this._render();
  }

  _render() {
    const monthNames = ["Jan", "Feb", "M\u00e4r", "Apr", "Mai", "Jun",
      "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
    const now = new Date();
    const monthLabel = `${monthNames[now.getMonth()]} ${now.getFullYear()}`;

    this.shadowRoot.innerHTML = `
<style>
:host {
  --sf: var(--card-background-color, #12121a);
  --bd: rgba(255,255,255,0.06);
  --sf2: #1a1a28;
  --tx: var(--primary-text-color, #e0e0e0);
  --tx2: var(--secondary-text-color, #9898a8);
  --ac: var(--accent-color, #4ecca3);
  display: block;
  margin-bottom: 24px;
}
.hdr {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
h1 {
  font-size: 24px;
  font-weight: 700;
  margin: 0;
  font-family: 'Segoe UI', system-ui, sans-serif;
}
.right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ts {
  font-size: 11px;
  color: var(--tx2);
}
.btn {
  padding: 7px 14px;
  border-radius: 10px;
  border: 1px solid var(--bd);
  background: var(--sf);
  color: var(--tx);
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
}
.btn:hover { background: var(--sf2); }
.btn:disabled { opacity: .5; cursor: default; }
.btn-p {
  background: var(--ac);
  color: #0a0a0f;
  border-color: var(--ac);
  font-weight: 600;
}
</style>
<div class="hdr">
  <h1>Finance Dashboard</h1>
  <div class="right">
    <span class="ts" id="ts"></span>
    <button class="btn" id="monthBtn">${monthLabel}</button>
    <button class="btn btn-p" id="refreshBtn">Aktualisieren</button>
  </div>
</div>`;

    this.shadowRoot.getElementById("refreshBtn")
      .addEventListener("click", () => {
        this.dispatchEvent(new CustomEvent("fd-refresh-requested", {
          bubbles: true,
          composed: true,
        }));
      });

    this._updateTimestamp();
  }

  _updateTimestamp() {
    const el = this.shadowRoot.getElementById("ts");
    if (!el) return;
    if (this._lastRefresh) {
      const d = new Date(this._lastRefresh);
      el.textContent = `Zuletzt: ${d.toLocaleTimeString("de-DE")}`;
    }
  }
}

customElements.define("fd-header", FdHeader);
