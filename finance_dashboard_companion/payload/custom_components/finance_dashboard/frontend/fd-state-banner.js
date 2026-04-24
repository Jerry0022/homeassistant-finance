/**
 * fd-state-banner — Persistent top-of-dashboard state banner.
 *
 * Surfaces states the user has to see before the KPI cards, so they
 * don't wonder "why are the numbers off?" — today, yesterday's
 * unreflected cash transaction, or a rate-limited refresh.
 *
 * States (first-match wins, ordered by urgency):
 *   1. rate_limited — amber, countdown to unlock
 *   2. cache_stale  — amber, prompt to refresh
 *   3. uncategorized — blue, nudge to open the categorisation wizard
 *
 * The banner is idempotent — feeding the same diagnostics snapshot
 * twice doesn't re-render. It's also dismissable per-session (click
 * the × to hide until the panel reloads); a state change re-shows it.
 *
 * Input: `diag` property — the full snapshot from GET /diagnostics.
 * Events: none (read-only display, user triggers actions via buttons).
 */

class FdStateBanner extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._diag = null;
    this._currentState = null;  // which state is shown right now
    this._dismissedFor = new Set();  // state keys the user hid
    this._rendered = false;
  }

  set diag(v) {
    this._diag = v || null;
    this._update();
  }

  connectedCallback() {
    this._render();
    this._update();
  }

  _chooseState(d) {
    if (!d || d.error) return null;

    // Don't nag in demo mode — everything there is fake.
    if (d.demo_mode) return null;

    if (d.rate_limited_until) {
      const end = new Date(d.rate_limited_until);
      if (end.getTime() > Date.now()) {
        const dateStr = end.toLocaleString("de-DE", {
          day: "2-digit", month: "2-digit",
          hour: "2-digit", minute: "2-digit",
        });
        return {
          key: "rate_limited",
          kind: "warn",
          icon: "⏱",
          title: "Tageslimit der Bank-API erreicht",
          message: `Cache bleibt aktiv. Neue Live-Daten ab ${dateStr}.`,
          action: null,
        };
      }
    }

    if (d.cache_stale && d.has_cache) {
      const hours = Math.floor((d.cache_age_seconds || 0) / 3600);
      return {
        key: "cache_stale",
        kind: "warn",
        icon: "⚠",
        title: `Daten sind ${hours} Std alt`,
        message: "Klicke oben auf \u201eAktualisieren\u201c um frische Bankdaten zu holen.",
        action: null,
      };
    }

    const uncat = d.uncategorized_count || 0;
    if (uncat >= 5) {
      return {
        key: "uncategorized",
        kind: "info",
        icon: "🏷",
        title: `${uncat} Transaktionen sind nicht kategorisiert`,
        message: "Öffne die Kategorisierungs-Karte um sie zuzuordnen — "
          + "verbessert Budget-Analysen automatisch.",
        action: null,
      };
    }

    return null;
  }

  _update() {
    if (!this._rendered) return;
    const state = this._chooseState(this._diag);
    const root = this.shadowRoot.getElementById("root");
    if (!root) return;

    const stateKey = state?.key || null;
    if (stateKey && this._dismissedFor.has(stateKey)) {
      // User hid this exact state — wait for a state change.
      root.innerHTML = "";
      this._currentState = null;
      return;
    }
    if (!state) {
      root.innerHTML = "";
      this._currentState = null;
      return;
    }
    if (this._currentState === stateKey) {
      // Already rendered this exact state — skip re-render to avoid
      // animation re-trigger on each 60 s diagnostics poll.
      return;
    }
    this._currentState = stateKey;

    root.innerHTML = `
<div class="banner banner-${state.kind}" role="status" aria-live="polite">
  <div class="icon" aria-hidden="true">${state.icon}</div>
  <div class="body">
    <div class="title">${this._esc(state.title)}</div>
    <div class="msg">${this._esc(state.message)}</div>
  </div>
  <button class="close" aria-label="Hinweis schließen" id="close">✕</button>
</div>`;
    root.querySelector("#close")?.addEventListener("click", () => {
      if (this._currentState) {
        this._dismissedFor.add(this._currentState);
      }
      root.innerHTML = "";
      this._currentState = null;
    });
  }

  _esc(s) {
    if (s == null) return "";
    const d = document.createElement("div");
    d.textContent = String(s);
    return d.innerHTML;
  }

  _render() {
    this._rendered = true;
    this.shadowRoot.innerHTML = `
<style>
:host {
  display: block;
  margin-bottom: 16px;
  font-family: 'Segoe UI', system-ui, sans-serif;
}
.banner {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 14px 18px;
  border-radius: 12px;
  border: 1px solid;
  animation: fade-in 0.3s ease-out;
}
@keyframes fade-in {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}
.banner-warn {
  border-color: rgba(243,156,18,0.35);
  background: rgba(243,156,18,0.08);
  color: #f39c12;
}
.banner-info {
  border-color: rgba(59,130,246,0.35);
  background: rgba(59,130,246,0.08);
  color: #3b82f6;
}
.icon {
  font-size: 20px;
  line-height: 1;
  flex-shrink: 0;
  margin-top: 1px;
}
.body { flex: 1; min-width: 0; }
.title {
  font-size: 14px;
  font-weight: 600;
  color: var(--primary-text-color, #e0e0e0);
  margin-bottom: 2px;
}
.msg {
  font-size: 13px;
  color: var(--secondary-text-color, #9898a8);
  line-height: 1.4;
}
.close {
  background: none;
  border: none;
  color: var(--secondary-text-color, #9898a8);
  font-size: 16px;
  cursor: pointer;
  padding: 0 6px;
  line-height: 1;
  margin-left: 6px;
  flex-shrink: 0;
}
.close:hover { color: var(--primary-text-color, #e0e0e0); }
</style>
<div id="root"></div>`;
  }
}

customElements.define("fd-state-banner", FdStateBanner);
