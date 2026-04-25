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
    const { tSync } = window._fd;
    if (this._rateLimitedUntil && new Date(this._rateLimitedUntil) > new Date()) {
      btn.disabled = true;
      btn.textContent = tSync("header.refresh.rate_limited");
      btn.title = tSync("header.refresh.rate_limited_title");
    } else if (this._refreshing) {
      btn.disabled = true;
      btn.textContent = tSync("header.refresh.refreshing");
      btn.title = tSync("header.refresh.refreshing");
    } else {
      btn.disabled = false;
      btn.textContent = tSync("header.refresh.button");
      btn.title = tSync("header.refresh.button_title");
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
    // Once we have a timestamp, update the "N min ago" label every 60s
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
    const { tSync } = window._fd;
    btn.setAttribute("aria-pressed", String(this._demoMode));
    if (this._demoMode) {
      btn.textContent = tSync("header.demo_on");
      btn.classList.add("btn-demo-active");
      if (badge) badge.style.display = "inline-block";
    } else {
      btn.textContent = tSync("header.demo_off");
      btn.classList.remove("btn-demo-active");
      if (badge) badge.style.display = "none";
    }
  }

  _render() {
    const { SHARED_CSS, tSync } = window._fd;
    const now = new Date();
    const lang = (window._fd._hass && window._fd._hass.language)
      || navigator.language || "en";
    const monthLabel = now.toLocaleDateString(lang, { month: "short", year: "numeric" });

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
.month-label {
  padding: 7px 14px;
  border-radius: 10px;
  border: 1px solid var(--bd);
  background: var(--sf);
  color: var(--tx2);
  font-size: 13px;
  cursor: default;
  user-select: none;
  font-family: inherit;
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
      <span class="ts empty" id="ts">${tSync("header.ts.empty")}</span>
      <span class="ts-stats" id="tsStats"></span>
    </div>
    <button class="btn btn-demo" id="demoBtn" aria-label="${tSync("header.demo_toggle")}" aria-pressed="false">${tSync("header.demo_off")}</button>
    <span class="month-label" id="monthLabel" aria-label="Aktueller Monat: ${monthLabel}">${monthLabel}</span>
    <button class="btn btn-p" id="refreshBtn">${tSync("header.refresh.button")}</button>
    <button class="btn" id="addAccountBtn" title="${tSync("header.add_account_title")}">${tSync("header.add_account")}</button>
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
    const { tSync } = window._fd;
    const lang = (window._fd._hass && window._fd._hass.language)
      || navigator.language || "en";

    // Refresh in flight takes priority over everything else.
    if (this._refreshing) {
      el.className = "ts loading";
      el.textContent = tSync("header.ts.loading");
      if (statsEl) statsEl.textContent = "";
      return;
    }

    // Hard rate-limit state — surface it where the user looks first.
    if (this._rateLimitedUntil && new Date(this._rateLimitedUntil) > new Date()) {
      el.className = "ts rate";
      el.textContent = tSync("header.ts.rate");
      if (statsEl) {
        const next = new Date(this._rateLimitedUntil);
        statsEl.textContent = tSync("header.ts.rate_next", {
          date: next.toLocaleDateString(lang),
        });
      }
      return;
    }

    if (this._lastRefresh) {
      const d = new Date(this._lastRefresh);
      const timeStr = d.toLocaleTimeString(lang, {
        hour: "2-digit", minute: "2-digit",
      });
      const dayStr = d.toLocaleDateString(lang, {
        day: "2-digit", month: "2-digit",
      });
      const ageMin = Math.max(0, Math.round((Date.now() - d.getTime()) / 60000));
      let ageLabel;
      if (ageMin < 1) ageLabel = tSync("header.ts.age.now");
      else if (ageMin < 60) ageLabel = tSync("header.ts.age.min", { n: ageMin });
      else if (ageMin < 1440) {
        const h = Math.round(ageMin / 60);
        ageLabel = tSync("header.ts.age.hour", { n: h });
      } else {
        const days = Math.round(ageMin / 1440);
        ageLabel = tSync("header.ts.age.day", { n: days });
      }
      el.className = "ts";
      el.textContent = tSync("header.ts.last", { time: timeStr, age: ageLabel });
      el.title = `${dayStr} ${timeStr}`;

      if (statsEl) {
        const s = this._lastRefreshStats;
        if (s && s.outcome) {
          const parts = [];
          if (s.accounts != null) parts.push(`${s.accounts} ${tSync("general.accounts_plural")}`);
          if (s.transactions != null) parts.push(`${s.transactions} Tx`);
          if (s.new) parts.push(`${s.new} ${tSync("general.new")}`);
          if (s.outcome === "partial") parts.push(tSync("general.partial_error"));
          else if (s.outcome === "rate_limited") parts.push(tSync("general.rate_limit"));
          else if (s.outcome === "error") parts.push(tSync("general.error"));
          statsEl.textContent = parts.join(" · ");
        } else {
          statsEl.textContent = "";
        }
      }
      return;
    }

    // No cache at all.
    el.className = "ts empty";
    el.textContent = tSync("header.ts.empty");
    if (statsEl) statsEl.textContent = "";
  }
}

customElements.define("fd-header", FdHeader);
