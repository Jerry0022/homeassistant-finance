/**
 * fd-diagnostics — Collapsible transparency widget for the Finance Dashboard.
 *
 * Always-visible summary bar + expandable details showing:
 *   - Cache age + last refresh timestamp
 *   - Rate-limit state (midnight unblock countdown)
 *   - Refresh stats (outcome, accounts, transactions, new, duration, errors)
 *   - Per-bank session status
 *   - Per-account cached data (balance, transaction count, linked entity)
 *   - Entity group overview with live entity_ids resolved from registry
 *
 * Data source: GET /api/finance_dashboard/diagnostics (cache-only, no bank call).
 * Auto-refreshes on hass state change, on parent fd-data-updated, and every 60 s.
 *
 * Properties:
 *   hass — Home Assistant object, required for the API call + registry lookup
 */
const DOMAIN = "finance_dashboard";
const POLL_INTERVAL_MS = 60_000;

class FdDiagnostics extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._diag = null;
    this._entityRegistry = new Map(); // entity_id -> unique_id
    this._loadingRegistry = false;
    this._expanded = false;
    this._pollTimer = null;
    this._fetchInFlight = false;
    this._lastFetchFailed = false;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._loadEntityRegistry();
      this._fetchDiagnostics();
      this._pollTimer = setInterval(() => this._fetchDiagnostics(), POLL_INTERVAL_MS);
    }
  }

  disconnectedCallback() {
    if (this._pollTimer) clearInterval(this._pollTimer);
    this._pollTimer = null;
  }

  /** Public — parent calls this after a successful refresh to pull fresh state. */
  refresh() {
    return this._fetchDiagnostics();
  }

  async _loadEntityRegistry() {
    if (!this._hass?.connection || this._loadingRegistry) return;
    this._loadingRegistry = true;
    try {
      const registry = await this._hass.connection.sendMessagePromise({
        type: "config/entity_registry/list",
      });
      this._entityRegistry.clear();
      for (const entry of registry) {
        if (entry.platform === DOMAIN) {
          this._entityRegistry.set(entry.unique_id, entry.entity_id);
        }
      }
    } catch (e) {
      console.warn("fd-diagnostics: entity registry load failed:", e);
    } finally {
      this._loadingRegistry = false;
      this._render();
    }
  }

  async _fetchDiagnostics() {
    if (!this._hass || this._fetchInFlight) return;
    this._fetchInFlight = true;
    try {
      const resp = await this._hass.callApi("GET", `${DOMAIN}/diagnostics`);
      this._diag = resp;
      this._lastFetchFailed = false;
      // Broadcast so the state-banner (or any other listener) can
      // react without making its own API call.
      this.dispatchEvent(new CustomEvent("fd-diagnostics-updated", {
        detail: resp,
        bubbles: true,
        composed: true,
      }));
    } catch (e) {
      console.warn("fd-diagnostics: /diagnostics fetch failed:", e);
      this._lastFetchFailed = true;
    } finally {
      this._fetchInFlight = false;
      this._render();
    }
  }

  _esc(s) {
    if (s == null) return "";
    const d = document.createElement("div");
    d.textContent = String(s);
    return d.innerHTML;
  }

  _fmtAgeLong(seconds) {
    if (seconds == null) return "nie";
    if (seconds < 60) return "gerade eben";
    const m = Math.round(seconds / 60);
    if (m < 60) return `vor ${m} Min`;
    const h = Math.round(m / 60);
    if (h < 24) return `vor ${h} Std`;
    const d = Math.round(h / 24);
    return `vor ${d} Tg`;
  }

  _fmtAbsDE(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return d.toLocaleString("de-DE", {
        day: "2-digit", month: "2-digit", year: "numeric",
        hour: "2-digit", minute: "2-digit",
      });
    } catch { return iso; }
  }

  _fmtDur(ms) {
    if (ms == null) return "—";
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  }

  _fmtEUR(v, currency) {
    const num = typeof v === "string" ? parseFloat(v) : v;
    if (num == null || isNaN(num)) return "—";
    try {
      return new Intl.NumberFormat("de-DE", {
        style: "currency",
        currency: currency || "EUR",
      }).format(num);
    } catch { return `${num}`; }
  }

  _outcomeLabel(outcome) {
    switch (outcome) {
      case "ok": return { label: "Erfolgreich", cls: "ok" };
      case "partial": return { label: "Teilweise erfolgreich", cls: "warn" };
      case "rate_limited": return { label: "Tageslimit erreicht", cls: "warn" };
      case "error": return { label: "Fehler", cls: "err" };
      case "demo": return { label: "Demo", cls: "info" };
      default: return { label: outcome || "—", cls: "info" };
    }
  }

  _summaryText(d) {
    if (!d) return "Lade Diagnose …";
    if (d.error === "Not configured") return "Noch nicht konfiguriert";
    if (d.rate_limited_until) {
      const end = new Date(d.rate_limited_until);
      return `Tageslimit erreicht · neu ab ${end.toLocaleDateString("de-DE")} 00:00`;
    }
    if (!d.has_cache) {
      return "Cache leer — klicke \u201eAktualisieren\u201c";
    }
    const age = this._fmtAgeLong(d.cache_age_seconds);
    const accs = d.account_count ?? 0;
    const txs = d.transaction_count ?? 0;
    return `Cache ${age} · ${accs} Konten · ${txs} Transaktionen`;
  }

  _summaryIcon(d) {
    if (!d || d.error) return "warn";
    if (d.rate_limited_until) return "warn";
    if (d.is_refreshing) return "spin";
    if (!d.has_cache) return "info";
    const age = d.cache_age_seconds ?? Infinity;
    if (age > 24 * 3600) return "warn";
    return "ok";
  }

  _render() {
    const d = this._diag;
    const icon = this._summaryIcon(d);
    const summary = this._esc(this._summaryText(d));

    const statsHtml = this._renderStats(d);
    const rateHtml = this._renderRateLimit(d);
    const banksHtml = this._renderBanks(d);
    const accountsHtml = this._renderAccounts(d);
    const entitiesHtml = this._renderEntities(d);

    this.shadowRoot.innerHTML = `
<style>
:host {
  --sf: var(--card-background-color, #12121a);
  --sf2: #1a1a28;
  --bd: rgba(255,255,255,0.06);
  --tx: var(--primary-text-color, #e0e0e0);
  --tx2: var(--secondary-text-color, #9898a8);
  --ac: var(--accent-color, #4ecca3);
  --dg: #e74c3c;
  --wn: #f39c12;
  --bl: #3b82f6;
  display: block;
  margin-top: 24px;
  font-family: 'Segoe UI', system-ui, sans-serif;
  color: var(--tx);
}
.card {
  background: var(--sf);
  border: 1px solid var(--bd);
  border-radius: 14px;
  overflow: hidden;
}
.bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  cursor: pointer;
  user-select: none;
  background: var(--sf);
  transition: background 0.15s;
}
.bar:hover { background: var(--sf2); }
.bar-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--tx);
  letter-spacing: 0.2px;
}
.bar-summary {
  flex: 1;
  font-size: 13px;
  color: var(--tx2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bar-chev {
  width: 10px;
  height: 10px;
  border-right: 2px solid var(--tx2);
  border-bottom: 2px solid var(--tx2);
  transform: rotate(-45deg);
  transition: transform 0.25s;
}
.card.open .bar-chev { transform: rotate(45deg); }
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot.ok { background: var(--ac); box-shadow: 0 0 8px rgba(78,204,163,0.4); }
.dot.warn { background: var(--wn); box-shadow: 0 0 8px rgba(243,156,18,0.4); }
.dot.err { background: var(--dg); }
.dot.info { background: var(--tx2); }
.dot.spin {
  background: transparent;
  border: 2px solid rgba(78,204,163,0.3);
  border-top-color: var(--ac);
  animation: spin 0.8s linear infinite;
  box-sizing: border-box;
}
@keyframes spin { to { transform: rotate(360deg); } }

.details {
  display: none;
  border-top: 1px solid var(--bd);
  padding: 4px 0 0;
}
.card.open .details { display: block; }

.section {
  padding: 14px 18px;
  border-bottom: 1px solid var(--bd);
}
.section:last-child { border-bottom: none; }
.section-h {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--tx2);
  margin-bottom: 10px;
}
.kv {
  display: grid;
  grid-template-columns: minmax(120px, 180px) 1fr;
  gap: 6px 14px;
  font-size: 13px;
}
.kv dt { color: var(--tx2); }
.kv dd { margin: 0; color: var(--tx); }
.kv dd.ok { color: var(--ac); }
.kv dd.warn { color: var(--wn); }
.kv dd.err { color: var(--dg); }
.kv dd.mono {
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  font-size: 12px;
  color: var(--tx2);
  word-break: break-all;
}
.pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}
.pill.ok { background: rgba(78,204,163,0.12); color: var(--ac); }
.pill.warn { background: rgba(243,156,18,0.12); color: var(--wn); }
.pill.err { background: rgba(231,76,60,0.12); color: var(--dg); }
.pill.info { background: rgba(152,152,168,0.12); color: var(--tx2); }

.row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px dashed var(--bd);
}
.row:last-child { border-bottom: none; }
.row-logo {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--sf2);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
  font-size: 12px;
  color: var(--tx2);
}
.row-logo img { width: 100%; height: 100%; object-fit: contain; }
.row-main { flex: 1; min-width: 0; }
.row-title { font-size: 13px; font-weight: 500; color: var(--tx); }
.row-sub {
  font-size: 11px;
  color: var(--tx2);
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 2px;
}
.row-meta {
  text-align: right;
  font-size: 12px;
  color: var(--tx2);
  flex-shrink: 0;
}
.row-meta .num {
  color: var(--tx);
  font-weight: 600;
}

.entity-id {
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  font-size: 11px;
  color: var(--tx2);
  background: var(--sf2);
  padding: 2px 6px;
  border-radius: 4px;
  word-break: break-all;
}
.entity-group {
  margin-bottom: 10px;
}
.entity-group:last-child { margin-bottom: 0; }
.entity-group-h {
  font-size: 12px;
  font-weight: 600;
  color: var(--tx);
  margin-bottom: 4px;
  display: flex;
  justify-content: space-between;
}
.entity-group-h .count {
  color: var(--tx2);
  font-weight: 400;
  font-size: 11px;
}
.entity-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.empty {
  font-size: 12px;
  color: var(--tx2);
  font-style: italic;
  padding: 4px 0;
}
.errors-list {
  margin: 6px 0 0;
  padding: 0;
  list-style: none;
}
.errors-list li {
  font-size: 12px;
  color: var(--dg);
  background: rgba(231,76,60,0.06);
  padding: 6px 10px;
  border-radius: 6px;
  margin-top: 4px;
  word-break: break-word;
}
.refetch-btn {
  background: none;
  border: 1px solid var(--bd);
  color: var(--tx2);
  padding: 4px 10px;
  border-radius: 8px;
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
}
.refetch-btn:hover { background: var(--sf2); color: var(--tx); }
</style>

<section class="card ${this._expanded ? "open" : ""}" id="card">
  <div class="bar" id="bar" role="button" aria-expanded="${this._expanded}">
    <span class="dot ${icon}" aria-hidden="true"></span>
    <span class="bar-title">Diagnose</span>
    <span class="bar-summary" title="${summary}">${summary}</span>
    <span class="bar-chev" aria-hidden="true"></span>
  </div>
  <div class="details" id="details">
    ${statsHtml}
    ${rateHtml}
    ${banksHtml}
    ${accountsHtml}
    ${entitiesHtml}
  </div>
</section>`;

    this.shadowRoot.getElementById("bar")
      ?.addEventListener("click", () => this._toggle());

    this.shadowRoot.querySelectorAll("[data-action=refetch]").forEach((el) =>
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        this._fetchDiagnostics();
      }),
    );
  }

  _toggle() {
    this._expanded = !this._expanded;
    const card = this.shadowRoot.getElementById("card");
    if (card) card.classList.toggle("open", this._expanded);
    const bar = this.shadowRoot.getElementById("bar");
    if (bar) bar.setAttribute("aria-expanded", String(this._expanded));
    if (this._expanded) {
      this._fetchDiagnostics();
    }
  }

  _renderStats(d) {
    if (!d) {
      return `<div class="section">
        <div class="section-h">Letzter Refresh</div>
        <div class="empty">Lade …</div>
      </div>`;
    }
    const s = d.stats || {};
    const outcome = this._outcomeLabel(s.outcome);
    const errors = Array.isArray(s.errors) ? s.errors : [];

    const rows = [];
    if (s.outcome) {
      rows.push(
        `<dt>Ergebnis</dt>`
        + `<dd><span class="pill ${outcome.cls}">${this._esc(outcome.label)}</span></dd>`,
      );
    } else {
      rows.push(`<dt>Ergebnis</dt><dd class="warn">Noch kein Refresh durchgeführt</dd>`);
    }
    rows.push(
      `<dt>Zuletzt</dt><dd>${this._esc(this._fmtAbsDE(d.last_refresh))}`
      + ` <span style="color:var(--tx2)">(${this._esc(this._fmtAgeLong(d.cache_age_seconds))})</span></dd>`,
    );
    if (s.duration_ms != null) {
      rows.push(`<dt>Dauer</dt><dd>${this._esc(this._fmtDur(s.duration_ms))}</dd>`);
    }
    if (s.accounts != null) {
      rows.push(
        `<dt>Konten abgerufen</dt><dd>`
        + `<span class="num">${s.accounts}</span></dd>`,
      );
    }
    if (s.transactions != null) {
      const newPart = s.new
        ? ` <span style="color:var(--ac)">(+${s.new} neu)</span>`
        : "";
      rows.push(
        `<dt>Transaktionen geladen</dt><dd>`
        + `<span class="num">${s.transactions}</span>${newPart}</dd>`,
      );
    }
    rows.push(
      `<dt>Cache gesamt</dt>`
      + `<dd><span class="num">${d.account_count ?? 0}</span> Konten · `
      + `<span class="num">${d.transaction_count ?? 0}</span> Transaktionen</dd>`,
    );
    if (d.demo_mode) {
      rows.push(`<dt>Modus</dt><dd><span class="pill info">Demo aktiv</span></dd>`);
    }
    if (d.is_refreshing) {
      rows.push(`<dt>Status</dt><dd class="ok">Aktualisierung läuft gerade …</dd>`);
    }

    const errList = errors.length
      ? `<ul class="errors-list">${errors
          .map((e) => `<li>${this._esc(e)}</li>`)
          .join("")}</ul>`
      : "";

    return `<div class="section">
      <div class="section-h">
        <span>Letzter Refresh</span>
      </div>
      <dl class="kv">${rows.join("")}</dl>
      ${errList}
    </div>`;
  }

  _renderRateLimit(d) {
    if (!d) return "";
    const rl = d.rate_limited_until;
    if (!rl) {
      return `<div class="section">
        <div class="section-h">Rate Limit (Enable Banking)</div>
        <div class="kv">
          <dt>Status</dt>
          <dd class="ok"><span class="pill ok">OK</span> 4 Abfragen/Tag pro Bank</dd>
        </div>
      </div>`;
    }
    const end = new Date(rl);
    const dateStr = end.toLocaleString("de-DE", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
    const minsLeft = Math.max(0, Math.round((end.getTime() - Date.now()) / 60000));
    const hoursLeft = Math.round(minsLeft / 60);
    const until = hoursLeft >= 1
      ? `in ${hoursLeft} Std (${dateStr})`
      : `in ${minsLeft} Min (${dateStr})`;
    return `<div class="section">
      <div class="section-h">Rate Limit (Enable Banking)</div>
      <div class="kv">
        <dt>Status</dt>
        <dd class="warn"><span class="pill warn">Tageslimit erreicht</span></dd>
        <dt>Neu verfügbar</dt>
        <dd>${this._esc(until)}</dd>
        <dt>Limit</dt>
        <dd>4 Live-Abfragen/Tag pro Bank (Enable Banking PSD2)</dd>
      </div>
    </div>`;
  }

  _renderBanks(d) {
    const banks = d?.banks || [];
    if (!banks.length) {
      return `<div class="section">
        <div class="section-h">Banken</div>
        <div class="empty">Noch keine Bank verbunden</div>
      </div>`;
    }
    const rows = banks.map((b) => {
      const sess = b.session_configured
        ? `<span class="pill ok">Session aktiv</span>`
        : `<span class="pill warn">Keine Session</span>`;
      const logo = b.logo
        ? `<img src="${this._esc(b.logo)}" alt="">`
        : `<span>${this._esc((b.institution_name || "?")[0])}</span>`;
      return `<div class="row">
        <div class="row-logo">${logo}</div>
        <div class="row-main">
          <div class="row-title">${this._esc(b.institution_name || b.institution_id)}</div>
          <div class="row-sub">
            ${sess}
            <span>${b.account_count} Konto${b.account_count === 1 ? "" : "s"}</span>
          </div>
        </div>
      </div>`;
    }).join("");
    const maxDays = d.session_max_days ?? 180;
    return `<div class="section">
      <div class="section-h">Banken (${banks.length})</div>
      ${rows}
      <div class="empty" style="margin-top:8px">
        PSU-Session max. ${maxDays} Tage gültig (EU RTS 2022/2360).
      </div>
    </div>`;
  }

  _renderAccounts(d) {
    const accs = d?.accounts || [];
    if (!accs.length) {
      return `<div class="section">
        <div class="section-h">Konten (Cache-Inhalt)</div>
        <div class="empty">Noch keine Konten verbunden</div>
      </div>`;
    }
    const rows = accs.map((a) => {
      const entityId = this._entityRegistry.get(a.entity_unique_id);
      const entityCell = entityId
        ? `<span class="entity-id">${this._esc(entityId)}</span>`
        : `<span class="pill warn">Entität fehlt</span>`;
      const balCell = a.has_balance
        ? `<span class="num">${this._esc(
            this._fmtEUR(a.balance_amount, a.balance_currency),
          )}</span>`
        : `<span class="pill warn">kein Kontostand</span>`;
      const logo = a.logo
        ? `<img src="${this._esc(a.logo)}" alt="">`
        : `<span>${this._esc((a.institution || "?")[0])}</span>`;
      const person = a.person ? ` · ${this._esc(a.person)}` : "";
      return `<div class="row">
        <div class="row-logo">${logo}</div>
        <div class="row-main">
          <div class="row-title">
            ${this._esc(a.name || "Unbekannt")}
            <span style="color:var(--tx2);font-weight:400">${this._esc(a.iban_masked)}</span>
          </div>
          <div class="row-sub">
            <span>${this._esc(a.institution || "—")}</span>
            <span>${this._esc(a.type || "personal")}${person}</span>
            ${entityCell}
          </div>
        </div>
        <div class="row-meta">
          ${balCell}<br>
          <span class="num">${a.transaction_count || 0}</span> Tx im Cache
        </div>
      </div>`;
    }).join("");
    return `<div class="section">
      <div class="section-h">Konten (${accs.length})</div>
      ${rows}
    </div>`;
  }

  _renderEntities(d) {
    const hints = d?.entity_hints || [];
    if (!hints.length) {
      return `<div class="section">
        <div class="section-h">Verknüpfte Entitäten</div>
        <div class="empty">Keine Entitäten vorhanden</div>
      </div>`;
    }
    const groups = hints.map((h) => {
      const ids = this._resolveEntityIds(h);
      const list = ids.length
        ? `<div class="entity-list">${ids
            .map((id) => `<span class="entity-id">${this._esc(id)}</span>`)
            .join("")}</div>`
        : `<div class="empty">noch nicht registriert</div>`;
      const countLabel = h.count_hint != null
        ? `${ids.length}/${h.count_hint}`
        : `${ids.length}`;
      return `<div class="entity-group">
        <div class="entity-group-h">
          <span>${this._esc(h.label)}</span>
          <span class="count">${countLabel}</span>
        </div>
        ${list}
      </div>`;
    }).join("");
    return `<div class="section">
      <div class="section-h">
        <span>Verknüpfte Entitäten</span>
        <button class="refetch-btn" data-action="refetch" style="float:right;margin-top:-2px">
          Neu laden
        </button>
      </div>
      ${groups}
    </div>`;
  }

  _resolveEntityIds(hint) {
    const ids = [];
    if (hint.unique_id) {
      const id = this._entityRegistry.get(hint.unique_id);
      if (id) ids.push(id);
      return ids;
    }
    if (hint.unique_ids) {
      for (const uid of hint.unique_ids) {
        const id = this._entityRegistry.get(uid);
        if (id) ids.push(id);
      }
      return ids;
    }
    if (hint.pattern_prefix || hint.pattern_suffix) {
      for (const [uid, entityId] of this._entityRegistry.entries()) {
        const prefixOk = hint.pattern_prefix
          ? uid.startsWith(hint.pattern_prefix)
          : true;
        const suffixOk = hint.pattern_suffix
          ? uid.endsWith(hint.pattern_suffix)
          : true;
        // Exclude aggregate sensors when matching generic *_balance suffix
        const isAggregate = uid === `${DOMAIN}_total_balance`
          || uid === `${DOMAIN}_monthly_summary`;
        if (prefixOk && suffixOk && !isAggregate) {
          ids.push(entityId);
        }
      }
    }
    return ids.sort();
  }
}

customElements.define("fd-diagnostics", FdDiagnostics);
