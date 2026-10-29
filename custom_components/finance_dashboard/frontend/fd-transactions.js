/**
 * fd-transactions — the transaction list (desktop only, a subpage).
 *
 * Extracted from fd-overview's transactions section (search, account filter, rows,
 * paging). Spec: docs/dev/ui-concept-gap.md § 1.6 / G19, VR-later 5. There is no mobile
 * entry: below 1024 px the page says it is a desktop view instead of loading ~650 rows.
 *
 *   <fd-transactions>   property: hass (required); attribute `embedded` = no own header
 *
 * Data (cache reads, never a bank call):
 *   GET finance_dashboard/transactions?q&account&limit&offset   admin only
 *       (non-admins get {privacy:"aggregate_only"} -> one quiet line, no rows)
 *   GET finance_dashboard/balances                              only the account names for the filter
 * IBANs appear masked only (last 4 digits), as the API delivers them.
 *
 * Overflow: text column `min-width:0`, remittance wraps anywhere (max 2 lines), meta line
 * ellipsizes, amount never shrinks. Fine at 375 px as well as on desktop.
 *
 * Events (bubbling, composed): fd-navigate {target:"back"} via the shared subpage header.
 */

const DOMAIN = "finance_dashboard";
const PAGE_SIZE = 25;
const DEBOUNCE_MS = 300;
const DESKTOP = "(min-width: 1024px)";

/*FB-START*/
const FB = {
  de: {
    "tx.title": "Transaktionen",
    "tx.search": "Suche in Verwendungszweck, Gegenpartei, Konto",
    "tx.search_label": "Transaktionen durchsuchen",
    "tx.all_accounts": "Alle Konten",
    "tx.account_label": "Konto filtern",
    "tx.empty": "Keine Transaktionen gefunden.",
    "tx.range": "$first–$last von $count",
    "tx.prev": "Zurück",
    "tx.next": "Weiter",
    "tx.pending": "vorgemerkt",
    "tx.admin_only": "Einzelne Transaktionen sind nur für Administratoren sichtbar.",
    "tx.error": "Transaktionen konnten nicht geladen werden.",
    "tx.retry": "Erneut versuchen",
    "tx.loading": "Wird geladen …",
    "tx.desktop_only": "Die Transaktionsliste gibt es nur am Desktop.",
  },
  en: {
    "tx.title": "Transactions",
    "tx.search": "Search purpose, counterparty, account",
    "tx.search_label": "Search transactions",
    "tx.all_accounts": "All accounts",
    "tx.account_label": "Filter by account",
    "tx.empty": "No transactions found.",
    "tx.range": "$first–$last of $count",
    "tx.prev": "Previous",
    "tx.next": "Next",
    "tx.pending": "pending",
    "tx.admin_only": "Individual transactions are visible to administrators only.",
    "tx.error": "Could not load transactions.",
    "tx.retry": "Try again",
    "tx.loading": "Loading …",
    "tx.desktop_only": "The transaction list is available on desktop only.",
  },
};
/*FB-END*/

function tr(key, vars = {}) {
  let s = window._fd.tSync(key, vars);
  if (s !== key) return s;
  const raw = ((window._fd._hass && window._fd._hass.language) || navigator.language || "en").toLowerCase();
  s = (FB[raw.startsWith("de") ? "de" : "en"][key]) || key;
  for (const [k, v] of Object.entries(vars)) s = s.replace(new RegExp(`\\$${k}`, "g"), String(v));
  return s;
}

const CSS = `
:host { display: block; min-width: 0; }
.root { container: tx / inline-size; color: var(--fd-t1); font-size: 13px; line-height: 1.4; min-width: 0; }
button, input, select { font: inherit; color: inherit; }
button { cursor: pointer; }
button:focus-visible, input:focus-visible, select:focus-visible { outline: 2px solid var(--fd-a500); outline-offset: 2px; }
.card { margin: 0 0 12px; padding: 12px 14px; border-radius: var(--fd-r-card); background: var(--fd-card); box-shadow: var(--fd-sh1); min-width: 0; }
.muted { color: var(--fd-t2); font-size: 11.5px; }
.empty { padding: 24px 12px; text-align: center; color: var(--fd-t2); }
.empty .btn { margin-top: 10px; }
.btn { display: inline-flex; align-items: center; justify-content: center; min-height: var(--fd-touch); padding: 0 16px; border: 1px solid transparent; border-radius: var(--fd-r-pill); background: var(--fd-a700); color: #fff; font-weight: 500; }
.btn.ghost { background: transparent; color: var(--fd-a700); border-color: var(--fd-a100); }
.btn:disabled { opacity: .5; cursor: default; }
.filters { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 8px; }
.filters input, .filters select { box-sizing: border-box; min-height: var(--fd-touch); padding: 0 12px; border: 1px solid var(--fd-line); border-radius: 10px; background: var(--fd-page); color: var(--fd-t1); max-width: 100%; }
.filters input { flex: 2 1 220px; min-width: 0; }
.filters select { flex: 1 1 200px; min-width: 0; text-overflow: ellipsis; }
.row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 2px 12px; padding: 8px 0; }
.row + .row { border-top: 1px solid var(--fd-line); }
.row .l { min-width: 0; }
.row .p { font-weight: 500; overflow-wrap: anywhere; }
.row .d { color: var(--fd-t2); font-size: 12px; overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.row .m { grid-column: 1 / -1; min-width: 0; color: var(--fd-t2); font-size: 11.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row .a { grid-column: 2; grid-row: 1; flex: none; text-align: right; white-space: nowrap; font-weight: 500; font-variant-numeric: tabular-nums; }
.row .a.in { color: var(--fd-ok); }
.row .ac::before { content: " · "; white-space: pre; }
.chip { display: inline-flex; padding: 0 8px; border-radius: var(--fd-r-pill); font-size: 10.5px; font-weight: 500; background: var(--fd-sunk); color: var(--fd-t2); white-space: nowrap; }
@container tx (min-width: 720px) {
  .row { grid-template-columns: 92px minmax(0, 1fr) minmax(0, 200px) auto; align-items: start; gap: 12px; }
  .row .m { display: contents; }
  .row .m .dt { grid-column: 1; grid-row: 1; }
  .row .l { grid-column: 2; grid-row: 1; }
  .row .ac::before { content: none; }
  .row .m .ac { grid-column: 3; grid-row: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .row .a { grid-column: 4; grid-row: 1; }
}
.pager { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; padding-top: 8px; border-top: 1px solid var(--fd-line); }
.pager .btns { display: flex; gap: 6px; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
.wide { display: none; }
.narrow { display: block; }
@media (min-width: 1024px) { .wide { display: block; } .narrow { display: none; } }
`;

class FdTransactions extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._accounts = [];
    this._tx = { items: [], total: 0, offset: 0 };
    this._status = "idle"; // idle | loading | ok | admin | error
    this._q = "";
    this._account = "";
    this._timer = null;
    this._seq = 0;
    this._built = false;
    this._mq = typeof matchMedia === "function" ? matchMedia(DESKTOP) : null;
    this._onMq = () => { if (this._mq.matches && this._status === "idle") this.reload(); };
  }

  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    if (first) this.reload();
  }
  get hass() { return this._hass; }

  get _isAdmin() { return !!(this._hass && this._hass.user && this._hass.user.is_admin); }
  get _desktop() { return !this._mq || this._mq.matches; }

  connectedCallback() { if (this._mq) this._mq.addEventListener("change", this._onMq); }
  disconnectedCallback() {
    clearTimeout(this._timer);
    if (this._mq) this._mq.removeEventListener("change", this._onMq);
  }

  /** Re-read accounts and the first page. */
  async reload() {
    if (!this._hass) return;
    await window._fd.t("tx.title");
    if (!this._built) { this._built = true; this._render(); }
    if (!this._desktop) return; // desktop-only: no 650-row fetch on a phone
    if (!this._isAdmin) { this._status = "admin"; this._render(); return; }
    try {
      const balances = await this._hass.callApi("GET", `${DOMAIN}/balances`);
      this._accounts = Object.entries(balances || {})
        .filter(([, a]) => a && typeof a === "object" && !a.error && a.account_key)
        .map(([id, a]) => ({ id, ...a }));
    } catch (_) {
      this._accounts = [];
    }
    await this._load(0);
  }

  async _load(offset) {
    const seq = ++this._seq;
    this._status = "loading";
    this._paintList();
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (this._q) params.set("q", this._q);
    if (this._account) params.set("account", this._account);
    try {
      const r = await this._hass.callApi("GET", `${DOMAIN}/transactions?${params}`);
      if (seq !== this._seq) return;
      if (r && r.privacy === "aggregate_only") {
        this._status = "admin";
        this._render();
        return;
      }
      this._tx = { items: (r && r.transactions) || [], total: (r && r.total) || 0, offset: (r && r.offset) || 0 };
      this._status = "ok";
    } catch (_) {
      if (seq !== this._seq) return;
      this._status = "error";
    }
    this._paintList();
  }

  _render() {
    if (!this._built) return;
    const { SHARED_CSS, escHtml: e } = window._fd;
    const head = this.hasAttribute("embedded") ? "" : `<fd-subpage-header title="${e(tr("tx.title"))}"></fd-subpage-header>`;
    let inner;
    if (this._status === "admin") {
      inner = `<div class="card"><div class="empty">${e(tr("tx.admin_only"))}</div></div>`;
    } else {
      inner = `<div class="narrow card"><div class="empty">${e(tr("tx.desktop_only"))}</div></div>
<div class="wide card">
  <div class="filters">
    <label class="sr" for="q">${e(tr("tx.search_label"))}</label>
    <input id="q" type="search" placeholder="${e(tr("tx.search"))}" autocomplete="off" value="${e(this._q)}">
    <label class="sr" for="acct">${e(tr("tx.account_label"))}</label>
    <select id="acct">
      <option value="">${e(tr("tx.all_accounts"))}</option>
      ${this._accounts.map((a) => `<option value="${e(a.account_key)}"${a.account_key === this._account ? " selected" : ""}>${e(a.account_name || a.id)} (${e(a.iban_masked || "****")})</option>`).join("")}
    </select>
  </div>
  <div id="list"></div>
</div>`;
    }
    this.shadowRoot.innerHTML = `<style>${SHARED_CSS}${CSS}</style><div class="root">${head}${inner}</div>`;
    const q = this.shadowRoot.getElementById("q");
    if (q) {
      q.addEventListener("input", () => {
        clearTimeout(this._timer);
        this._timer = setTimeout(() => { this._q = q.value.trim(); this._load(0); }, DEBOUNCE_MS);
      });
      this.shadowRoot.getElementById("acct").addEventListener("change", (ev) => {
        this._account = ev.target.value;
        this._load(0);
      });
    }
    this._paintList();
  }

  /** Repaint only the list so the search field keeps focus while typing. */
  _paintList() {
    const list = this.shadowRoot && this.shadowRoot.getElementById("list");
    if (!list) return;
    const { escHtml: e, fmtDate } = window._fd;
    const t = this._tx;
    if (this._status === "loading" && !t.items.length) { list.innerHTML = `<div class="empty">${e(tr("tx.loading"))}</div>`; return; }
    if (this._status === "error") {
      list.innerHTML = `<div class="empty">${e(tr("tx.error"))}<br><button class="btn ghost" id="retry">${e(tr("tx.retry"))}</button></div>`;
      list.querySelector("#retry").addEventListener("click", () => this._load(t.offset));
      return;
    }
    if (!t.items.length) { list.innerHTML = `<div class="empty">${e(tr("tx.empty"))}</div>`; return; }
    const fmtAmt = (x) => {
      const n = parseFloat(x.amount);
      try { return new Intl.NumberFormat(undefined, { style: "currency", currency: x.currency || "EUR" }).format(n); }
      catch (_) { return `${x.amount} ${x.currency || ""}`; }
    };
    const rows = t.items.map((x) => {
      const n = parseFloat(x.amount);
      const party = x.creditor || x.debtor || "";
      const pend = x.status && x.status !== "booked" ? ` <span class="chip">${e(tr("tx.pending"))}</span>` : "";
      return `<div class="row">
  <div class="l"><div class="p">${e(party)}${pend}</div><div class="d">${e(x.description)}</div></div>
  <div class="a ${n > 0 ? "in" : ""}">${e(fmtAmt(x))}</div>
  <div class="m"><span class="dt">${e(fmtDate(x.date))}</span><span class="ac">${e(x.account_name || "")}</span></div>
</div>`;
    });
    const from = t.offset + 1;
    const to = t.offset + t.items.length;
    list.innerHTML = `${rows.join("")}
<div class="pager">
  <span class="muted">${e(tr("tx.range", { first: from, last: to, count: t.total }))}</span>
  <span class="btns">
    <button class="btn ghost" id="prev" ${t.offset <= 0 ? "disabled" : ""}>${e(tr("tx.prev"))}</button>
    <button class="btn ghost" id="next" ${to >= t.total ? "disabled" : ""}>${e(tr("tx.next"))}</button>
  </span>
</div>`;
    list.querySelector("#prev").addEventListener("click", () => this._load(Math.max(0, t.offset - PAGE_SIZE)));
    list.querySelector("#next").addEventListener("click", () => this._load(t.offset + PAGE_SIZE));
  }
}

window._fd.defineOnce("fd-transactions", FdTransactions);
