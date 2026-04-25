/**
 * fd-header — Title bar with month selector, refresh button, status chip, toast.
 *
 * Properties:
 *   lastRefresh       {string} — ISO timestamp of last successful refresh
 *   refreshing        {bool}   — live fetch in flight
 *   rateLimitedUntil  {string} — ISO timestamp; if future, refresh is blocked
 *   lastRefreshStats  {object} — {outcome, accounts, transactions, new, duration_ms, errors}
 *   demoMode          {bool}
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
    this._rateLimitedUntil = null;
    this._demoMode = false;
    this._lastRefreshStats = null;
    this._timestampTimer = null;
    this._toastTimer = null;
  }

  set lastRefresh(v) {
    this._lastRefresh = v;
    this._updateTimestamp();
    this._scheduleTimestampTick();
  }

  set refreshing(v) {
    this._refreshing = v;
    this._updateRefreshBtn();
    this._updateTimestamp();
  }

  set rateLimitedUntil(v) {
    this._rateLimitedUntil = v;
    this._updateRefreshBtn();
    this._updateTimestamp();
  }

  set lastRefreshStats(v) {
    this._lastRefreshStats = v;
    this._updateTimestamp();
  }

  set demoMode(v) {
    this._demoMode = v;
    this._updateDemoBtn();
  }

  _updateRefreshBtn() {
    const btn = this.shadowRoot.getElementById("refreshBtn");
    if (!btn) return;
    if (this._rateLimitedUntil && new Date(this._rateLimitedUntil) > new Date()) {
      btn.disabled = true;
      btn.textContent = "Morgen verf\u00fcgbar";
      btn.title = "Tageslimit der Bank-API erreicht (4/Tag pro Konto). N\u00e4chste Aktualisierung ab morgen.";
    } else if (this._refreshing) {
      btn.disabled = true;
      btn.textContent = "L\u00e4dt\u2026";
      btn.title = "Bank-API wird abgefragt\u2014dies kann einige Sekunden dauern.";
    } else {
      btn.disabled = false;
      btn.textContent = "Aktualisieren";
      btn.title = "Live-Daten von der Bank-API holen";
    }
  }

  connectedCallback() {
    this._render();
  }

  disconnectedCallback() {
    if (this._timestampTimer) clearInterval(this._timestampTimer);
    if (this._toastTimer) clearTimeout(this._toastTimer);
  }

  _scheduleTimestampTick() {
    // Once we have a timestamp, update the "vor N min" label every 60s
    // so the user always sees the current cache age without reloading.
    if (this._timestampTimer || !this._lastRefresh) return;
    this._timestampTimer = setInterval(() => this._updateTimestamp(), 60000);
  }

  /** Public: show a toast with refresh results. */
  showToast(message, kind) {
    const toast = this.shadowRoot.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.className = `toast toast-${kind || "info"} show`;
    // aria-live: assertive for warn/error, polite for info/success
    const liveValue = (kind === "warn" || kind === "error") ? "assertive" : "polite";
    toast.setAttribute("aria-live", liveValue);
    if (this._toastTimer) clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      toast.classList.remove("show");
    }, kind === "error" ? 7000 : 4500);
  }

  _updateDemoBtn() {
    const btn = this.shadowRoot.getElementById("demoBtn");
    const badge = this.shadowRoot.getElementById("demoBadge");
    if (!btn) return;
    btn.setAttribute("aria-pressed", String(this._demoMode));
    if (this._demoMode) {
      btn.textContent = "Demo aus";
      btn.classList.add("btn-demo-active");
      if (badge) badge.style.display = "inline-block";
    } else {
      btn.textContent = "Demo";
      btn.classList.remove("btn-demo-active");
      if (badge) badge.style.display = "none";
    }
  }

  _render() {
    const { MONTH_NAMES, SHARED_CSS } = window._fd;
    const now = new Date();
    const monthLabel = `${MONTH_NAMES[now.getMonth()]} ${now.getFullYear()}`;

    const LOCAL_CSS = `
:host {
  --demo: var(--wn, #f39c12);
  margin-bottom: 24px;
}
.hdr {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
h1 {
  font-size: 24px;
  font-weight: 700;
  margin: 0;
  font-family: 'Segoe UI', system-ui, sans-serif;
}
.demo-badge {
  display: none;
  padding: 3px 10px;
  border-radius: 6px;
  background: var(--demo);
  color: var(--bg, #0a0a0f);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
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
  color: var(--bg, #0a0a0f);
  border-color: var(--ac);
  font-weight: 600;
}
.btn-demo {
  /* Neutral ghost style — matches secondary buttons, no orange hint */
  border-color: var(--bd);
  background: var(--sf);
  color: var(--tx2);
}
.btn-demo:hover {
  background: var(--sf2);
  color: var(--tx);
}
.btn-demo-active {
  /* Filled orange only when demo mode is ON */
  border-color: var(--demo);
  background: var(--demo);
  color: var(--bg, #0a0a0f);
  font-weight: 600;
}
.btn-demo-active:hover {
  background: color-mix(in srgb, var(--demo) 85%, black);
  border-color: color-mix(in srgb, var(--demo) 85%, black);
}
.ts-stack {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  line-height: 1.2;
}
.ts-stats {
  font-size: 10px;
  color: var(--tx2);
  opacity: 0.85;
}
.ts.loading { color: var(--ac); }
.ts.empty   { color: var(--tx2); font-style: italic; }
.ts.rate    { color: var(--demo); }

/* Toast */
.toast {
  position: fixed;
  top: 18px;
  right: 18px;
  z-index: 2000;
  padding: 10px 18px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  background: var(--sf);
  color: var(--tx);
  border: 1px solid var(--bd);
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  opacity: 0;
  transform: translateY(-10px);
  pointer-events: none;
  transition: opacity 0.25s, transform 0.25s;
  max-width: 360px;
  white-space: pre-wrap;
}
.toast.show { opacity: 1; transform: translateY(0); }
.toast-success { border-color: var(--ac); }
.toast-info    { border-color: color-mix(in srgb, var(--ac) 30%, transparent); }
.toast-warn    { border-color: var(--demo); color: var(--demo); }
.toast-error   { border-color: var(--dg); color: var(--dg); }

@media (max-width: 600px) {
  .hdr { flex-wrap: wrap; gap: 10px; }
  .right { width: 100%; justify-content: flex-end; }
  h1 { font-size: 20px; }
  .btn { padding: 6px 10px; font-size: 12px; }
}
`;

    this.shadowRoot.innerHTML = `
<style>${SHARED_CSS}${LOCAL_CSS}</style>
<div class="toast" id="toast" role="status" aria-live="polite" aria-atomic="true"></div>
<div class="hdr">
  <div class="title-row">
    <h1>Finance Dashboard</h1>
    <span class="demo-badge" id="demoBadge">DEMO</span>
  </div>
  <div class="right">
    <div class="ts-stack">
      <span class="ts empty" id="ts">Noch keine Daten \u2014 klicke "Aktualisieren"</span>
      <span class="ts-stats" id="tsStats"></span>
    </div>
    <button class="btn btn-demo" id="demoBtn" aria-label="Demo-Modus umschalten" aria-pressed="false">Demo</button>
    <button class="btn" id="monthBtn">${monthLabel}</button>
    <button class="btn btn-p" id="refreshBtn">Aktualisieren</button>
    <button class="btn" id="addAccountBtn" title="Bankkonto hinzuf\u00fcgen">+ Konto</button>
  </div>
</div>`;

    this.shadowRoot.getElementById("refreshBtn")
      .addEventListener("click", () => {
        this.dispatchEvent(new CustomEvent("fd-refresh-requested", {
          bubbles: true,
          composed: true,
        }));
      });

    this.shadowRoot.getElementById("demoBtn")
      .addEventListener("click", () => {
        this.dispatchEvent(new CustomEvent("fd-demo-toggle", {
          bubbles: true,
          composed: true,
        }));
      });

    this.shadowRoot.getElementById("addAccountBtn")
      .addEventListener("click", () => {
        this.dispatchEvent(new CustomEvent("fd-open-wizard", {
          bubbles: true,
          composed: true,
        }));
      });

    this._updateTimestamp();
    this._updateDemoBtn();
  }

  _updateTimestamp() {
    const el = this.shadowRoot.getElementById("ts");
    const statsEl = this.shadowRoot.getElementById("tsStats");
    if (!el) return;

    // Refresh in flight takes priority over everything else.
    if (this._refreshing) {
      el.className = "ts loading";
      el.textContent = "Aktualisiere\u2026 Bank-API wird abgefragt";
      if (statsEl) statsEl.textContent = "";
      return;
    }

    // Hard rate-limit state — surface it where the user looks first.
    if (this._rateLimitedUntil && new Date(this._rateLimitedUntil) > new Date()) {
      el.className = "ts rate";
      el.textContent = "Tageslimit erreicht \u2014 Cache wird genutzt";
      if (statsEl) {
        const next = new Date(this._rateLimitedUntil);
        statsEl.textContent = `Neue Abfragen ab ${next.toLocaleDateString("de-DE")} 00:00`;
      }
      return;
    }

    if (this._lastRefresh) {
      const d = new Date(this._lastRefresh);
      const timeStr = d.toLocaleTimeString("de-DE", {
        hour: "2-digit", minute: "2-digit",
      });
      const dayStr = d.toLocaleDateString("de-DE", {
        day: "2-digit", month: "2-digit",
      });
      const ageMin = Math.max(0, Math.round((Date.now() - d.getTime()) / 60000));
      let ageLabel;
      if (ageMin < 1) ageLabel = "gerade eben";
      else if (ageMin < 60) ageLabel = `vor ${ageMin} Min`;
      else if (ageMin < 1440) {
        const h = Math.round(ageMin / 60);
        ageLabel = `vor ${h} Std`;
      } else {
        const days = Math.round(ageMin / 1440);
        ageLabel = `vor ${days} Tg`;
      }
      el.className = "ts";
      el.textContent = `Zuletzt: ${timeStr} (${ageLabel})`;
      el.title = `Letzte Aktualisierung: ${dayStr} ${timeStr}`;

      if (statsEl) {
        const s = this._lastRefreshStats;
        if (s && s.outcome) {
          const parts = [];
          if (s.accounts != null) parts.push(`${s.accounts} Konten`);
          if (s.transactions != null) parts.push(`${s.transactions} Tx`);
          if (s.new) parts.push(`${s.new} neu`);
          if (s.outcome === "partial") parts.push("teilweise Fehler");
          else if (s.outcome === "rate_limited") parts.push("Rate-Limit");
          else if (s.outcome === "error") parts.push("Fehler");
          statsEl.textContent = parts.join(" \u00b7 ");
        } else {
          statsEl.textContent = "";
        }
      }
      return;
    }

    // No cache at all.
    el.className = "ts empty";
    el.textContent = "Noch keine Daten \u2014 klicke \"Aktualisieren\"";
    if (statsEl) statsEl.textContent = "";
  }
}

customElements.define("fd-header", FdHeader);
