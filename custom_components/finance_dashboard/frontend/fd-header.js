/**
 * fd-header — Overview action bar (freshness, demo, refresh, add bank) and the toast host.
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

  /** Members cannot import, toggle demo or add banks: those calls are admin-only. */
  _applyRole() {
    const h = window._fd && window._fd._hass;
    const admin = !!(h && h.user && h.user.is_admin);
    for (const id of ["refreshBtn", "demoBtn", "addAccountBtn"]) {
      const el = this.shadowRoot.getElementById(id);
      if (el) el.hidden = !admin;
    }
  }

  _updateRefreshBtn() {
    this._applyRole();
    const btn = this.shadowRoot.getElementById("refreshBtn");
    if (!btn) return;
    const { tSync } = window._fd;
    // A click is always an attended request: the backend sends PSU headers,
    // and PSD2 RTS Art. 36(5)(b) caps only unattended access.  So a standing
    // background rate limit must NOT disable the button — it only warns.
    if (this._rateLimitedUntil && new Date(this._rateLimitedUntil) > new Date()) {
      btn.disabled = false;
      btn.textContent = tSync("header.refresh.button");
      btn.setAttribute("data-tip", tSync("header.refresh.rate_limited_title"));
    } else if (this._refreshing) {
      btn.disabled = true;
      btn.textContent = tSync("header.refresh.refreshing");
      btn.setAttribute("data-tip", tSync("header.refresh.refreshing"));
    } else {
      btn.disabled = false;
      btn.textContent = tSync("header.refresh.button");
      btn.setAttribute("data-tip", tSync("header.refresh.button_title"));
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

    const LOCAL_CSS = `
:host { margin-bottom: 12px; color: var(--fd-t1); font-size: 13px; line-height: 1.4; }
/* The shell shows the action bar only on the Overview tab; elsewhere it is just the toast host. */
:host([toast-only]) { margin-bottom: 0; }
:host([toast-only]) .hdr { display: none; }
button, a { font: inherit; cursor: pointer; }
.hdr {
  display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 12px;
  padding: 10px 14px; border-radius: var(--fd-r-card); background: var(--fd-card); box-shadow: var(--fd-sh1);
}
.ts-stack { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1 1 200px; }
.ts { font-size: 12.5px; color: var(--fd-t1); }
.ts-stats { font-size: 11.5px; color: var(--fd-t2); }
.ts.loading { color: var(--fd-a700); }
.ts.empty { color: var(--fd-t2); }
.ts.rate { color: var(--fd-over); }
.right { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; min-width: 0; }
.demo-badge {
  display: none; padding: 1px 9px; border-radius: var(--fd-r-pill); font-size: 11px; font-weight: 500;
  background: var(--fd-desktop-bg); color: var(--fd-desktop);
}
.btn {
  display: inline-flex; align-items: center; justify-content: center; min-height: var(--fd-touch);
  padding: 0 16px; border: 1px solid var(--fd-a100); border-radius: var(--fd-r-pill);
  background: transparent; color: var(--fd-a700); font-weight: 500; text-decoration: none;
}
.btn:hover { background: var(--fd-a50); }
.btn-p { background: var(--fd-a700); color: #fff; border-color: transparent; }
.btn-p:hover { background: var(--fd-a900); }
.btn:disabled { opacity: .5; cursor: default; }
.btn-demo-active { background: var(--fd-desktop-bg); color: var(--fd-desktop); border-color: var(--fd-desktop); border-style: dashed; }
.btn-demo-active:hover { background: var(--fd-desktop-bg); }
.btn:focus-visible { outline: 2px solid var(--fd-a500); outline-offset: 2px; }
/* data-tip tooltips anchor at the right edge so they never leave the viewport */
.btn[data-tip]::after { left: auto; right: 0; transform: none; }

/* Toast */
.toast {
  position: fixed; top: 16px; left: 50%; z-index: 2000; max-width: min(360px, calc(100vw - 32px));
  padding: 10px 16px; border: 1px solid var(--fd-line); border-left: 4px solid var(--fd-a500);
  border-radius: var(--fd-r-pill); background: var(--fd-card); color: var(--fd-t1);
  box-shadow: var(--fd-sh2); font-size: 12.5px; font-weight: 500; white-space: pre-wrap;
  opacity: 0; transform: translate(-50%, -10px); pointer-events: none; transition: opacity .25s, transform .25s;
}
.toast.show { opacity: 1; transform: translate(-50%, 0); }
.toast-success { border-left-color: var(--fd-ok); }
.toast-info { border-left-color: var(--fd-a500); }
.toast-warn { border-left-color: var(--fd-attn); }
.toast-error { border-left-color: var(--fd-over); }
@media (max-width: 600px) {
  .right { width: 100%; }
  .right .btn { flex: 1 1 auto; padding: 0 12px; }
}
`;

    this.shadowRoot.innerHTML = `
<style>${SHARED_CSS}${LOCAL_CSS}</style>
<div class="toast" id="toast" role="status" aria-live="polite" aria-atomic="true"></div>
<div class="hdr">
  <div class="right">
    <span class="demo-badge" id="demoBadge">DEMO</span>
    <div class="ts-stack">
      <span class="ts empty" id="ts">${tSync("header.ts.empty")}</span>
      <span class="ts-stats" id="tsStats"></span>
    </div>
    <button class="btn btn-demo" id="demoBtn" aria-label="${tSync("header.demo_toggle")}" aria-pressed="false">${tSync("header.demo_off")}</button>
    <button class="btn btn-p" id="refreshBtn" data-tip="${tSync("header.refresh.button_title")}">${tSync("header.refresh.button")}</button>
    <a class="btn" id="addAccountBtn" data-tip="${tSync("header.add_account_title")}" href="${window._fd.INTEGRATION_PATH}" aria-label="${tSync("header.add_account_title")}">${tSync("header.add_account")}</a>
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
      .addEventListener("click", (ev) => {
        window._fd.navigate(window._fd.INTEGRATION_PATH, ev);
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
      el.setAttribute("aria-label", `${dayStr} ${timeStr}`);

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

window._fd.defineOnce("fd-header", FdHeader);
