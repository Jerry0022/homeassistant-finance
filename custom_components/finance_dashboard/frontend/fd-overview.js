/**
 * fd-overview — facts: people & household, bank connections, transactions, assignment.
 *
 * Accounts are aggregated under persons and the household (shared accounts);
 * single accounts are listed only on desktop (purple marker). Self-contained:
 * it reads cache endpoints and never triggers a live bank call itself
 * (the header's Refresh button does that through the panel).
 *
 *   GET finance_dashboard/balances      accounts + booked/available + last_update
 *   GET finance_dashboard/bank_status   per bank: consent, fetch budget, errors
 *   GET finance_dashboard/assignments   admin only: persons, account owners
 *   GET finance_dashboard/transactions  admin only; q/account/limit/offset
 *
 * Properties:  hass (required), reload() re-reads everything.
 * Contains <fd-settings> ("Personen & Konten"); reloads on fd-assignments-saved.
 */

const DOMAIN = "finance_dashboard";
const PAGE_SIZE = 25;
const SEARCH_DEBOUNCE_MS = 300;
const PERSON_COLORS = ["var(--fd-person-a)", "var(--fd-person-b)", "#ef6c00", "#5e35b1", "#6d4c41"];

// Fallback texts until locales/*.json carry the new ov.* keys.
const FB = {
  de: {
    "ov.persons.title": "Personen & Haushalt",
    "ov.persons.household": "Haushalt",
    "ov.persons.open": "Noch offen",
    "ov.persons.all": "Alle Konten",
    "ov.persons.accounts_one": "1 Konto",
    "ov.persons.accounts_other": "$n Konten",
    "ov.persons.available": "Verfügbar $amount",
    "ov.persons.desktop_tag": "Nur am Desktop",
    "ov.persons.detail": "Einzelne Konten",
    "ov.persons.empty": "Sobald eine Bank verbunden ist, erscheinen hier Personen und Haushalt.",
    "ov.unassigned.one": "1 Konto ist noch niemandem zugeordnet",
    "ov.unassigned.other": "$n Konten sind noch niemandem zugeordnet",
    "ov.unassigned.action": "Jetzt zuordnen",
    "ov.import.btn": "Neu importieren",
    "ov.import.busy": "Importiere …",
    "ov.import.tip": "Holt Rohdaten von der Bank und wertet sie aus. Zählt nicht gegen das automatische Limit.",
    "ov.reprocess.btn": "Aktualisieren",
    "ov.reprocess.busy": "Aktualisiere …",
    "ov.reprocess.tip": "Wertet die gespeicherten Rohdaten neu aus. Kein Bankabruf.",
    "ov.reprocess.ok": "Aktualisiert — $tx Buchungen aus $snapshots Abrufen neu ausgewertet (Version $version).",
    "ov.reprocess.empty": "Noch keine gespeicherten Rohdaten — „Neu importieren“ holt sie von der Bank.",
    "ov.reprocess.unavailable": "Aktualisieren ist gerade nicht möglich (kein Rohdaten-Archiv).",
    "ov.reprocess.error": "Aktualisieren fehlgeschlagen — die bisherigen Daten bleiben erhalten.",
    "ov.reprocess.admin": "Nur Administratoren können aktualisieren.",
    "ov.fresh.link": "Aktualität & Prüfung",
    "ov.fresh.last": "Zuletzt importiert: $date",
    "ov.fresh.never": "Noch nichts importiert",
  },
  en: {
    "ov.persons.title": "People & household",
    "ov.persons.household": "Household",
    "ov.persons.open": "Not assigned yet",
    "ov.persons.all": "All accounts",
    "ov.persons.accounts_one": "1 account",
    "ov.persons.accounts_other": "$n accounts",
    "ov.persons.available": "Available $amount",
    "ov.persons.desktop_tag": "Desktop only",
    "ov.persons.detail": "Individual accounts",
    "ov.persons.empty": "Once a bank is connected, people and household show up here.",
    "ov.unassigned.one": "1 account is not assigned to anyone yet",
    "ov.unassigned.other": "$n accounts are not assigned to anyone yet",
    "ov.unassigned.action": "Assign now",
    "ov.import.btn": "Import again",
    "ov.import.busy": "Importing …",
    "ov.import.tip": "Fetches raw data from the bank and processes it. Does not count against the automatic limit.",
    "ov.reprocess.btn": "Refresh",
    "ov.reprocess.busy": "Refreshing …",
    "ov.reprocess.tip": "Re-processes the stored raw data. No bank call.",
    "ov.reprocess.ok": "Refreshed — $tx bookings from $snapshots fetches re-evaluated (version $version).",
    "ov.reprocess.empty": "No stored raw data yet — \"Import again\" fetches it from the bank.",
    "ov.reprocess.unavailable": "Refreshing is not possible right now (no raw archive).",
    "ov.reprocess.error": "Refreshing failed — the previous data is kept.",
    "ov.reprocess.admin": "Only administrators can refresh.",
    "ov.fresh.link": "Freshness & checks",
    "ov.fresh.last": "Last import: $date",
    "ov.fresh.never": "Nothing imported yet",
  },
};

function tr(key, vars = {}) {
  let s = window._fd.tSync(key, vars);
  if (s !== key) return s;
  const raw = ((window._fd._hass && window._fd._hass.language) || navigator.language || "en").toLowerCase();
  s = (FB[raw.startsWith("de") ? "de" : "en"][key]) || key;
  for (const [k, v] of Object.entries(vars)) s = s.replace(new RegExp(`\\$${k}`, "g"), String(v));
  return s;
}

const CSS = `
:host { display: block; }
.root { container: ov / inline-size; color: var(--fd-t1); font-size: 13px; line-height: 1.4; }
button { font: inherit; color: inherit; cursor: pointer; }
section { margin: 0 0 16px; }
.card { margin: 0 0 12px; padding: 12px 14px; border: 0; border-radius: var(--fd-r-card); background: var(--fd-card); box-shadow: var(--fd-sh1); }
.h { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; margin: 0 0 8px; font-size: 14px; font-weight: 500; }
.muted { color: var(--fd-t2); font-size: 11.5px; }
.empty { padding: 24px 12px; text-align: center; color: var(--fd-t2); }
.err { color: var(--fd-over); }
.btn { display: inline-flex; align-items: center; justify-content: center; min-height: var(--fd-touch); padding: 0 16px; border: 1px solid transparent; border-radius: var(--fd-r-pill); background: var(--fd-a700); color: #fff; font-weight: 500; text-decoration: none; }
.btn.ghost { background: transparent; color: var(--fd-a700); border-color: var(--fd-a100); }
.btn.sm { min-height: 36px; padding: 0 12px; font-size: 12px; }
.btn:disabled { opacity: .5; cursor: default; }
button:focus-visible, a:focus-visible, input:focus-visible, select:focus-visible { outline: 2px solid var(--fd-a500); outline-offset: 2px; }
.dtag { display: inline-flex; align-items: center; gap: 4px; padding: 1px 8px; border-radius: var(--fd-r-pill); font-size: 10.5px; font-weight: 500; background: var(--fd-desktop-bg); color: var(--fd-desktop); }
.dtag::before { content: "\\25C6"; font-size: 8px; }
.st-ok { --cbg: var(--fd-ok-bg); --cfg: color-mix(in srgb, var(--fd-ok) 72%, var(--fd-t1)); }
.st-near { --cbg: var(--fd-near-bg); --cfg: color-mix(in srgb, var(--fd-near) 72%, var(--fd-t1)); }
.st-over { --cbg: var(--fd-over-bg); --cfg: color-mix(in srgb, var(--fd-over) 72%, var(--fd-t1)); }
.chip { display: inline-flex; align-items: center; gap: 4px; padding: 1px 9px; border-radius: var(--fd-r-pill); font-size: 11.5px; font-weight: 500; white-space: nowrap; background: var(--cbg); color: var(--cfg); }
.chip.pend { --cbg: var(--fd-sunk); --cfg: var(--fd-t2); margin-left: 4px; }

.banner { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin: 0 0 12px; padding: 8px 12px; border-left: 4px solid var(--fd-attn); border-radius: 10px; background: var(--fd-card); box-shadow: var(--fd-sh1); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
.grid .card { margin: 0; border-top: 4px solid var(--c, var(--fd-a500)); }
.pc .nm { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 500; overflow-wrap: anywhere; }
.pc .nm i { flex: none; width: 10px; height: 10px; border-radius: 50%; background: var(--c); }
.pc .big { margin: 6px 0 2px; font-size: 28px; font-weight: 500; line-height: 1.1; font-variant-numeric: tabular-nums; }
.pc .meta { display: flex; flex-wrap: wrap; gap: 2px 12px; color: var(--fd-t2); font-size: 11.5px; }
.pc .det { display: none; margin-top: 10px; padding-top: 8px; border-top: 1px dashed var(--fd-desktop); }
.pc .det .dh { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 4px; }
.pc .det .ar { display: flex; justify-content: space-between; gap: 8px; padding: 3px 0; font-size: 12px; }
.pc .det .ar span:first-child { min-width: 0; overflow-wrap: anywhere; }
.pc .det .ar span:last-child { white-space: nowrap; font-variant-numeric: tabular-nums; }
@container ov (min-width: 760px) { .pc .det { display: block; } }

.bk { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; padding: 10px 0; }
.bk + .bk { border-top: 1px solid var(--fd-line); }
.bk .nm { font-weight: 500; overflow-wrap: anywhere; }
.facts { display: flex; flex-wrap: wrap; gap: 2px 12px; margin-top: 4px; color: var(--fd-t2); font-size: 11.5px; overflow-wrap: anywhere; }
.facts .warn { color: var(--fd-over); }

.acts { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--fd-line); }
.acts .lastimp { flex: 1 1 100%; font-size: 11.5px; }
.filters { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 8px; }
.filters input, .filters select { box-sizing: border-box; min-height: var(--fd-touch); padding: 0 12px; border: 1px solid var(--fd-line); border-radius: 10px; background: var(--fd-page); color: var(--fd-t1); font: inherit; max-width: 100%; }
.filters input { flex: 1 1 200px; min-width: 0; }
.filters select { flex: 1 1 200px; }
.tx { display: flex; justify-content: space-between; gap: 10px; padding: 8px 0; }
.tx + .tx { border-top: 1px solid var(--fd-line); }
.tx .l { min-width: 0; flex: 1; }
.tx .p { font-weight: 500; overflow-wrap: anywhere; }
.tx .s { color: var(--fd-t2); font-size: 11.5px; overflow-wrap: anywhere; }
.tx .r { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
.tx .r .a { font-weight: 500; }
.tx .r .a.in { color: var(--fd-ok); }
.pager { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; padding-top: 8px; border-top: 1px solid var(--fd-line); }
.pager .btns { display: flex; gap: 6px; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
`;

class FdOverview extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._accounts = [];
    this._banks = [];
    this._assign = null;
    this._loaded = false;
    this._error = false;
    this._tx = { items: [], total: 0, offset: 0, error: false, loading: false };
    this._q = "";
    this._account = "";
    this._searchTimer = null;
    this._txSeq = 0;
    this._built = false;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this.reload();
  }

  get hass() {
    return this._hass;
  }

  get _isAdmin() {
    return !!(this._hass && this._hass.user && this._hass.user.is_admin);
  }

  disconnectedCallback() {
    clearTimeout(this._searchTimer);
  }

  /** Re-read all cache endpoints (cheap, never hits the bank). */
  async reload() {
    if (!this._hass) return;
    await window._fd.t("ov.loading"); // load the user's locale
    this._build();
    try {
      const [balances, status] = await Promise.all([
        this._hass.callApi("GET", `${DOMAIN}/balances`),
        this._hass.callApi("GET", `${DOMAIN}/bank_status`),
      ]);
      this._accounts = Object.entries(balances || {})
        .filter(([, a]) => a && typeof a === "object" && !a.error)
        .map(([id, a]) => ({ id, ...a }));
      this._banks = (status && status.banks) || [];
      this._lastImport = this._banks.map((b) => b.last_success).filter(Boolean).sort().pop() || null;
      this._error = false;
    } catch (e) {
      console.warn("fd-overview: load failed:", e);
      this._error = true;
    }
    this._assign = null;
    if (this._isAdmin) {
      try {
        this._assign = await this._hass.callApi("GET", `${DOMAIN}/assignments`);
      } catch (e) {
        console.warn("fd-overview: assignments unavailable:", e);
      }
    }
    this._loaded = true;
    this._renderTop();
    this._feedSettings();
    await this._loadTransactions(0);
  }

  _feedSettings() {
    const st = this.shadowRoot.querySelector("fd-settings");
    if (!st) return;
    if (this._assign) st.data = this._assign;
    st.hass = this._hass;
  }

  async _loadTransactions(offset) {
    const box = this.shadowRoot.getElementById("tx");
    if (!box) return;
    if (!this._isAdmin) {
      this._tx = { items: [], total: 0, offset: 0, error: false, admin: false };
      this._renderTx();
      return;
    }
    const seq = ++this._txSeq;
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (this._q) params.set("q", this._q);
    if (this._account) params.set("account", this._account);
    try {
      const resp = await this._hass.callApi("GET", `${DOMAIN}/transactions?${params}`);
      if (seq !== this._txSeq) return; // a newer request superseded this one
      this._tx = {
        items: (resp && resp.transactions) || [],
        total: (resp && resp.total) || 0,
        offset: (resp && resp.offset) || 0,
        error: false,
        admin: true,
      };
    } catch (e) {
      if (seq !== this._txSeq) return;
      this._tx = { items: [], total: 0, offset: 0, error: true, admin: true };
    }
    this._renderTx();
  }

  // -- rendering ---------------------------------------------------------

  _build() {
    if (this._built) return;
    this._built = true;
    const { SHARED_CSS, tSync } = window._fd;
    this.shadowRoot.innerHTML = `
<style>${SHARED_CSS}${CSS}</style>
<div class="root">
  <div id="banner"></div>
  <section id="persons"></section>
  <section id="banks"></section>
  <section id="txsec">
    <div class="card">
      <div class="h"><span>${tSync("ov.tx.title")}</span></div>
      <div id="tx"></div>
    </div>
  </section>
  <section id="settings">${this._isAdmin ? `<div class="card" id="setupEntry"><div class="h"><span>${tSync("setup.title")}</span></div>
    <button type="button" class="btn ghost" data-open-setup>${tSync("setup.entry")}</button></div>` : ""}<fd-settings></fd-settings></section>
</div>`;
    const sh = this.shadowRoot;
    sh.addEventListener("click", (ev) => {
      const a = ev.target.closest("[data-nav]");
      if (a) { window._fd.navigate(a.getAttribute("href") || window._fd.INTEGRATION_PATH, ev); return; }
      if (ev.target.closest("#btnImport")) { this.dispatchEvent(new CustomEvent("fd-refresh-requested", { bubbles: true, composed: true })); return; }
      if (ev.target.closest("#btnReprocess")) { this.reprocess(); return; }
      if (ev.target.closest("#btnFresh")) { this.dispatchEvent(new CustomEvent("fd-navigate", { bubbles: true, composed: true, detail: { target: "freshness" } })); return; }
      if (ev.target.closest("[data-open-setup]")) {
        this.dispatchEvent(new CustomEvent("fd-open-setup", { bubbles: true, composed: true }));
        return;
      }
      if (ev.target.closest("[data-goto-settings]")) {
        const el = sh.getElementById("settings");
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        el.querySelector("fd-settings")?.focus?.();
      }
    });
    sh.addEventListener("fd-assignments-saved", (ev) => {
      const p = ev.detail && ev.detail.payload;
      if (p) this._assign = p;
      this._renderTop();
    });
  }

  /** Groups: each person, household (shared), not-yet-assigned. Without
   *  assignment data (non-admin) everything is one "all accounts" group. */
  _groups() {
    const ownerOf = {};
    if (this._assign) for (const a of this._assign.accounts || []) ownerOf[a.key] = a.owner || "";
    const known = this._assign ? ownerOf : null;
    const groups = [];
    const mk = (id, label, color, accounts) => {
      let booked = 0, avail = 0, hasAvail = false, latest = "";
      for (const a of accounts) {
        const b = a.booked ? parseFloat(a.booked.amount) : NaN;
        const v = a.available ? parseFloat(a.available.amount) : NaN;
        if (!isNaN(b)) booked += b;
        if (!isNaN(v)) { avail += v; hasAvail = true; }
        if (a.last_update && a.last_update > latest) latest = a.last_update;
      }
      groups.push({ id, label, color, accounts, booked, avail: hasAvail ? avail : null, latest });
    };
    if (!known) {
      if (this._accounts.length) mk("all", tr("ov.persons.all"), "var(--fd-a500)", this._accounts);
      return groups;
    }
    const mine = (o) => this._accounts.filter((a) => (ownerOf[a.account_key] || "") === o);
    (this._assign.persons || []).forEach((p, i) => {
      mk("p:" + p.name, p.name, PERSON_COLORS[i % PERSON_COLORS.length], mine(p.name));
    });
    mk("shared", tr("ov.persons.household"), "var(--fd-household)", mine("shared"));
    mk("open", tr("ov.persons.open"), "var(--fd-t3)", mine(""));
    return groups.filter((g) => g.accounts.length || g.id.startsWith("p:") || g.id === "shared")
      .filter((g) => g.accounts.length || this._accounts.length);
  }

  _renderTop() {
    const { tSync, eur, escHtml, fmtDate } = window._fd;
    const per = this.shadowRoot.getElementById("persons");
    const banks = this.shadowRoot.getElementById("banks");
    const banner = this.shadowRoot.getElementById("banner");
    if (!per || !banks) return;

    if (this._error) {
      per.innerHTML = `<div class="card"><div class="empty err">${tSync("ov.error")}</div></div>`;
      banks.innerHTML = "";
      return;
    }

    // ---- unassigned banner ----
    const open = this._assign ? (this._assign.accounts || []).filter((a) => !a.owner).length : 0;
    banner.innerHTML = open
      ? `<div class="banner" role="status"><span>${escHtml(open === 1 ? tr("ov.unassigned.one") : tr("ov.unassigned.other", { n: open }))}</span>
          <button type="button" class="btn sm" data-goto-settings>${escHtml(tr("ov.unassigned.action"))}</button></div>`
      : "";

    // ---- persons & household ----
    const cards = this._groups().map((g) => {
      const n = g.accounts.length;
      const list = g.accounts.map((a) => {
        const b = a.booked ? parseFloat(a.booked.amount) : NaN;
        return `<div class="ar"><span>${escHtml(a.account_name)} · ${escHtml(a.iban_masked)}</span><span>${isNaN(b) ? "–" : eur(b)}</span></div>`;
      }).join("");
      return `<div class="card pc" style="--c:${g.color}">
  <div class="nm"><i></i>${escHtml(g.label)}</div>
  <div class="big">${n ? eur(g.booked) : "–"}</div>
  <div class="meta">
    <span>${escHtml(n === 1 ? tr("ov.persons.accounts_one") : tr("ov.persons.accounts_other", { n }))}</span>
    ${g.avail != null ? `<span>${escHtml(tr("ov.persons.available", { amount: eur(g.avail) }))}</span>` : ""}
    ${g.latest ? `<span>${escHtml(tSync("ov.accounts.updated", { date: fmtDate(g.latest, true) }))}</span>` : ""}
  </div>
  ${n ? `<div class="det"><div class="dh"><span class="muted">${escHtml(tr("ov.persons.detail"))}</span><span class="dtag">${escHtml(tr("ov.persons.desktop_tag"))}</span></div>${list}</div>` : ""}
</div>`;
    });
    per.innerHTML = `
<div class="h"><span>${tr("ov.persons.title")}</span></div>
${cards.length ? `<div class="grid">${cards.join("")}</div>`
  : `<div class="card"><div class="empty">${tr("ov.persons.empty")}
      <div style="margin-top:12px"><a class="btn" data-nav href="${window._fd.INTEGRATION_PATH}">${tSync("header.add_account")}</a></div></div></div>`}`;

    // ---- banks ----
    const bankRows = this._banks.map((b) => this._bankRow(b));
    banks.innerHTML = `
<div class="card">
  <div class="h"><span>${tSync("ov.banks.title")}</span>
    <a class="btn ghost sm" data-nav href="${window._fd.INTEGRATION_PATH}">${tSync("ov.banks.manage")}</a>
  </div>
  ${bankRows.length ? bankRows.join("") : `<div class="empty">${tSync("ov.banks.empty")}</div>`}
  ${this._isAdmin && bankRows.length ? this._actionsHtml() : ""}
</div>`;
    this._syncActions();

    this._renderFilters();
  }

  /** Import / refresh buttons of the bank card (admin only) + the link to the freshness page. */
  _actionsHtml() {
    const { escHtml, fmtDate } = window._fd;
    const last = this._lastImport ? tr("ov.fresh.last", { date: fmtDate(this._lastImport, true) }) : tr("ov.fresh.never");
    return `<div class="acts">
  <button type="button" class="btn" id="btnImport" data-tip="${escHtml(tr("ov.import.tip"))}">${escHtml(tr("ov.import.btn"))}</button>
  <button type="button" class="btn ghost" id="btnReprocess" data-tip="${escHtml(tr("ov.reprocess.tip"))}">${escHtml(tr("ov.reprocess.btn"))}</button>
  <button type="button" class="btn ghost" id="btnFresh">${escHtml(tr("ov.fresh.link"))}</button>
  <span class="muted lastimp">${escHtml(last)}</span>
</div>`;
  }

  /** Busy/disabled state of the two buttons (import comes from the panel, refresh is ours). */
  _syncActions() {
    const imp = this.shadowRoot.getElementById("btnImport");
    const rep = this.shadowRoot.getElementById("btnReprocess");
    const busy = !!(this._importing || this._reprocessing);
    if (imp) {
      imp.disabled = busy;
      imp.textContent = this._importing ? tr("ov.import.busy") : tr("ov.import.btn");
      imp.setAttribute("aria-busy", String(!!this._importing));
    }
    if (rep) {
      rep.disabled = busy;
      rep.textContent = this._reprocessing ? tr("ov.reprocess.busy") : tr("ov.reprocess.btn");
      rep.setAttribute("aria-busy", String(!!this._reprocessing));
    }
  }

  /** Set by the panel while an attended import runs. */
  set importing(v) { this._importing = !!v; this._syncActions(); }

  /** POST /reprocess: re-derive from stored raw data, never a bank call. The toast carries the stats. */
  async reprocess() {
    if (this._reprocessing || !this._hass) return;
    this._reprocessing = true;
    this._syncActions();
    const toast = (message, type) => this.dispatchEvent(new CustomEvent("fd-toast", { bubbles: true, composed: true, detail: { message, type } }));
    try {
      const r = await this._hass.callApi("POST", `${DOMAIN}/reprocess`);
      const st = (r && r.stats) || {};
      if (r && r.ok && st.outcome === "rebuilt") {
        toast(tr("ov.reprocess.ok", { tx: st.transactions ?? 0, snapshots: st.snapshots ?? 0, version: st.version ?? "" }), "success");
      } else if (r && r.ok) {
        toast(tr("ov.reprocess.empty"), "info");
      } else if (st.outcome === "unavailable") {
        toast(tr("ov.reprocess.unavailable"), "warn");
      } else {
        toast(tr("ov.reprocess.error"), "error");
      }
    } catch (e) {
      const denied = e && (e.status_code === 403 || (e.body && e.body.error === "admin_required"));
      toast(tr(denied ? "ov.reprocess.admin" : "ov.reprocess.error"), denied ? "warn" : "error");
    } finally {
      this._reprocessing = false;
      this._syncActions();
    }
    this.dispatchEvent(new CustomEvent("fd-reprocess-done", { bubbles: true, composed: true }));
    this.reload();
  }

  _bankRow(b) {
    const { tSync, escHtml, fmtDate } = window._fd;
    const state = b.consent_state || "ok";
    const until = fmtDate(b.consent_valid_until);
    let consent;
    if (state === "expired") consent = tSync("ov.banks.consent_expired", { date: until });
    else if (state === "expiring") consent = tSync("ov.banks.consent_expiring", { date: until });
    else if (until) consent = tSync("ov.banks.consent_ok", { date: until });
    else consent = tSync("ov.banks.consent_unknown");
    const badge = tSync(`ov.banks.badge_${state === "expired" || state === "expiring" ? state : "ok"}`);
    const cls = state === "expired" ? "st-over" : state === "expiring" ? "st-near" : "st-ok";
    const blocked = b.blocked_until && new Date(b.blocked_until) > new Date();
    const facts = [
      `<span>${escHtml(consent)}</span>`,
      `<span>${escHtml(tSync("ov.banks.budget", { used: b.budget_used_today ?? 0, limit: b.budget_limit ?? 4 }))}</span>`,
    ];
    // Manual fetches are uncapped, so the budget never counts them.
    if (b.last_attended_at) {
      facts.push(`<span>${escHtml(tSync("ov.banks.last_manual", { date: fmtDate(b.last_attended_at, true) }))}</span>`);
    }
    if (blocked) {
      facts.push(`<span class="warn">${escHtml(tSync("ov.banks.blocked", { date: fmtDate(b.blocked_until, true) }))}</span>`);
    }
    if (b.last_success) {
      facts.push(`<span>${escHtml(tSync("ov.banks.last_success", { date: fmtDate(b.last_success, true) }))}</span>`);
    }
    if (b.last_error) {
      facts.push(`<span class="warn">${escHtml(tSync("ov.banks.last_error", { error: b.last_error }))}</span>`);
    }
    const renew = state === "ok"
      ? ""
      : `<a class="btn sm" data-nav href="${window._fd.INTEGRATION_PATH}">${tSync("ov.banks.renew")}</a>`;
    return `
<div class="bk">
  <div style="min-width:0;flex:1">
    <div class="nm">${escHtml(b.title || "Bank")} <span class="chip ${cls}">${escHtml(badge)}</span></div>
    <div class="facts">${facts.join("")}</div>
  </div>
  ${renew}
</div>`;
  }

  _renderFilters() {
    const { tSync, escHtml } = window._fd;
    const box = this.shadowRoot.getElementById("tx");
    if (!box || !this._isAdmin) return;
    if (!box.querySelector(".filters")) {
      box.innerHTML = `
<div class="filters">
  <label class="sr" for="q">${tSync("ov.tx.search_label")}</label>
  <input id="q" type="search" placeholder="${escHtml(tSync("ov.tx.search"))}" autocomplete="off">
  <label class="sr" for="acct">${tSync("ov.tx.account_label")}</label>
  <select id="acct"></select>
</div>
<div id="txlist"></div>`;
      const q = box.querySelector("#q");
      q.addEventListener("input", () => {
        clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(() => {
          this._q = q.value.trim();
          this._loadTransactions(0);
        }, SEARCH_DEBOUNCE_MS);
      });
      box.querySelector("#acct").addEventListener("change", (e) => {
        this._account = e.target.value;
        this._loadTransactions(0);
      });
    }
    const sel = box.querySelector("#acct");
    const opts = [`<option value="">${escHtml(tSync("ov.tx.all_accounts"))}</option>`].concat(
      this._accounts
        .filter((a) => a.account_key)
        .map((a) => `<option value="${escHtml(a.account_key)}">${escHtml(a.account_name)} (${escHtml(a.iban_masked)})</option>`),
    );
    sel.innerHTML = opts.join("");
    sel.value = this._account;
  }

  _renderTx() {
    const { tSync, escHtml, fmtDate } = window._fd;
    const box = this.shadowRoot.getElementById("tx");
    if (!box) return;
    if (this._tx.admin === false) {
      box.innerHTML = `<div class="empty">${tSync("ov.tx.admin_only")}</div>`;
      return;
    }
    this._renderFilters();
    const list = box.querySelector("#txlist");
    if (!list) return;
    const t = this._tx;
    if (t.error) {
      list.innerHTML = `<div class="empty err">${tSync("ov.tx.error")}</div>`;
      return;
    }
    if (!t.items.length) {
      list.innerHTML = `<div class="empty">${tSync("ov.tx.empty")}</div>`;
      return;
    }
    const fmtAmt = (tx) => {
      const n = parseFloat(tx.amount);
      try {
        return new Intl.NumberFormat(undefined, { style: "currency", currency: tx.currency || "EUR" }).format(n);
      } catch (_) {
        return `${tx.amount} ${tx.currency || ""}`;
      }
    };
    const body = t.items.map((tx) => {
      const n = parseFloat(tx.amount);
      const party = tx.creditor || tx.debtor || "";
      const pending = tx.status && tx.status !== "booked"
        ? ` <span class="chip pend">${tSync("ov.tx.pending")}</span>` : "";
      return `<div class="tx">
  <div class="l"><div class="p">${escHtml(party)}${pending}</div><div class="s">${escHtml(tx.description)}</div></div>
  <div class="r"><div class="a ${n > 0 ? "in" : ""}">${escHtml(fmtAmt(tx))}</div><div class="s">${escHtml(fmtDate(tx.date))} · ${escHtml(tx.account_name)}</div></div>
</div>`;
    });
    const from = t.offset + 1;
    const to = t.offset + t.items.length;
    list.innerHTML = `
${body.join("")}
<div class="pager">
  <span class="muted">${escHtml(tSync("ov.tx.range", { first: from, last: to, count: t.total }))}</span>
  <span class="btns">
    <button class="btn ghost sm" id="prev" ${t.offset <= 0 ? "disabled" : ""}>${tSync("ov.tx.prev")}</button>
    <button class="btn ghost sm" id="next" ${to >= t.total ? "disabled" : ""}>${tSync("ov.tx.next")}</button>
  </span>
</div>`;
    list.querySelector("#prev").addEventListener("click", () => this._loadTransactions(Math.max(0, t.offset - PAGE_SIZE)));
    list.querySelector("#next").addEventListener("click", () => this._loadTransactions(t.offset + PAGE_SIZE));
  }
}

window._fd.defineOnce("fd-overview", FdOverview);
