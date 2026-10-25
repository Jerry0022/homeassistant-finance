/**
 * fd-overview — plain facts: accounts, bank status, transaction list.
 *
 * No interpretation, no household logic. Self-contained: it reads three
 * cache-read endpoints and never triggers a live bank call itself
 * (the header's Refresh button does that through the panel).
 *
 *   GET finance_dashboard/balances      accounts + booked/available + last_update
 *   GET finance_dashboard/bank_status   per bank: consent, fetch budget, errors
 *   GET finance_dashboard/transactions  admin only; q/account/limit/offset
 *
 * Properties:  hass (required), reload() re-reads everything.
 */

const DOMAIN = "finance_dashboard";
const PAGE_SIZE = 25;
const SEARCH_DEBOUNCE_MS = 300;

class FdOverview extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._accounts = [];
    this._banks = [];
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
      this._error = false;
    } catch (e) {
      console.warn("fd-overview: load failed:", e);
      this._error = true;
    }
    this._loaded = true;
    this._renderTop();
    await this._loadTransactions(0);
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
<style>${SHARED_CSS}
:host { display: block; }
section { margin-bottom: var(--sp-xl); }
.card { overflow: hidden; }
.card-h .actions { display: flex; gap: var(--sp-sm); align-items: center; }
.muted { color: var(--tx2); font-size: var(--fs-md); }
.empty { padding: var(--sp-xl); text-align: center; color: var(--tx2); }
.row { display: flex; justify-content: space-between; gap: var(--sp-lg);
  padding: var(--sp-md) 18px; border-bottom: 1px solid var(--bd); align-items: flex-start; }
.row:last-child { border-bottom: none; }
.grow { flex: 1; min-width: 0; }
.name { font-weight: 600; font-size: 14px; overflow-wrap: anywhere; }
.sub { color: var(--tx2); font-size: var(--fs-sm); margin-top: 2px; overflow-wrap: anywhere; }
.amt { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.amt .big { font-size: var(--fs-lg); font-weight: 700; }
.total { padding: var(--sp-md) 18px; display: flex; justify-content: space-between;
  border-top: 1px solid var(--bd); font-weight: 600; }
.facts { display: flex; flex-wrap: wrap; gap: 2px var(--sp-lg); margin-top: var(--sp-xs);
  color: var(--tx2); font-size: var(--fs-sm); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: var(--fs-sm);
  font-weight: 600; border: 1px solid var(--bd); color: var(--tx2); }
.badge.ok { color: var(--ac); border-color: color-mix(in srgb, var(--ac) 40%, transparent); }
.badge.expiring { color: var(--wn); border-color: color-mix(in srgb, var(--wn) 50%, transparent); }
.badge.expired { color: var(--dg); border-color: color-mix(in srgb, var(--dg) 50%, transparent); }
.warn { color: var(--wn); }
.err { color: var(--dg); }
.btn { padding: 6px 12px; border-radius: 10px; border: 1px solid var(--bd); background: var(--sf);
  color: var(--tx); font-size: var(--fs-md); cursor: pointer; font-family: inherit;
  text-decoration: none; display: inline-block; }
.btn:hover { background: var(--sf2); }
.btn:disabled { opacity: .5; cursor: default; }
.btn-p { background: var(--ac); color: var(--bg); border-color: var(--ac); font-weight: 600; }
a.link { color: var(--ac); text-decoration: underline; cursor: pointer; }
.filters { display: flex; gap: var(--sp-sm); padding: var(--sp-md) 18px; flex-wrap: wrap;
  border-bottom: 1px solid var(--bd); }
input, select { background: var(--bg); color: var(--tx); border: 1px solid var(--bd);
  border-radius: 10px; padding: 7px 10px; font-size: var(--fs-md); font-family: inherit; }
input { flex: 1; min-width: 180px; }
select { max-width: 100%; }
table { width: 100%; border-collapse: collapse; font-size: var(--fs-md); }
th { text-align: left; color: var(--tx2); font-weight: 500; font-size: var(--fs-sm);
  padding: var(--sp-sm) var(--sp-md); border-bottom: 1px solid var(--bd); }
th.r, td.r { text-align: right; }
td { padding: var(--sp-sm) var(--sp-md); border-bottom: 1px solid var(--bd); vertical-align: top; }
td.date, td.r { white-space: nowrap; font-variant-numeric: tabular-nums; }
td .p { overflow-wrap: anywhere; }
.pager { display: flex; justify-content: space-between; align-items: center;
  padding: var(--sp-md) 18px; gap: var(--sp-sm); }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
@media (max-width: 640px) {
  .row { flex-direction: column; gap: var(--sp-xs); }
  .amt { text-align: left; }
  th.acc, td.acc { display: none; }
}
</style>
<section id="accounts"></section>
<section id="banks"></section>
<section id="txsec">
  <div class="card">
    <div class="card-h"><span>${tSync("ov.tx.title")}</span></div>
    <div id="tx"></div>
  </div>
</section>`;
    const sh = this.shadowRoot;
    sh.addEventListener("click", (ev) => {
      const a = ev.target.closest("[data-nav]");
      if (a) window._fd.navigate(a.getAttribute("href") || window._fd.INTEGRATION_PATH, ev);
    });
  }

  _renderTop() {
    const { tSync, eur, escHtml, fmtDate } = window._fd;
    const acc = this.shadowRoot.getElementById("accounts");
    const banks = this.shadowRoot.getElementById("banks");
    if (!acc || !banks) return;

    if (this._error) {
      acc.innerHTML = `<div class="card"><div class="empty err">${tSync("ov.error")}</div></div>`;
      banks.innerHTML = "";
      return;
    }

    // ---- accounts ----
    let total = 0;
    const rows = this._accounts.map((a) => {
      const booked = a.booked ? parseFloat(a.booked.amount) : NaN;
      const avail = a.available ? parseFloat(a.available.amount) : NaN;
      if (!isNaN(booked)) total += booked;
      const upd = a.last_update
        ? tSync("ov.accounts.updated", { date: fmtDate(a.last_update, true) })
        : tSync("ov.accounts.never");
      return `
<div class="row">
  <div class="grow">
    <div class="name">${escHtml(a.account_name)}</div>
    <div class="sub">${escHtml(a.institution)} · ${escHtml(a.iban_masked)}</div>
    <div class="sub">${escHtml(upd)}</div>
  </div>
  <div class="amt">
    <div class="big ${booked < 0 ? "neg" : ""}">${isNaN(booked) ? "–" : eur(booked)}</div>
    <div class="sub">${tSync("ov.accounts.booked")}</div>
    ${isNaN(avail) ? "" : `<div class="sub">${tSync("ov.accounts.available")}: ${eur(avail)}</div>`}
  </div>
</div>`;
    });
    acc.innerHTML = `
<div class="card">
  <div class="card-h"><span>${tSync("ov.accounts.title")}</span></div>
  ${rows.length ? rows.join("") : `<div class="empty">${tSync("ov.accounts.empty")}
    <div style="margin-top:12px"><a class="btn btn-p" data-nav href="${window._fd.INTEGRATION_PATH}">${tSync("header.add_account")}</a></div></div>`}
  ${rows.length > 1 ? `<div class="total"><span>${tSync("ov.accounts.total")}</span><span>${eur(total)}</span></div>` : ""}
</div>`;

    // ---- banks ----
    const bankRows = this._banks.map((b) => this._bankRow(b));
    banks.innerHTML = `
<div class="card">
  <div class="card-h"><span>${tSync("ov.banks.title")}</span>
    <span class="actions"><a class="btn" data-nav href="${window._fd.INTEGRATION_PATH}">${tSync("ov.banks.manage")}</a></span>
  </div>
  ${bankRows.length ? bankRows.join("") : `<div class="empty">${tSync("ov.banks.empty")}</div>`}
</div>`;

    // account filter options (needs the account list)
    this._renderFilters();
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
    const blocked = b.blocked_until && new Date(b.blocked_until) > new Date();
    const facts = [
      `<span class="${state === "ok" ? "" : state === "expired" ? "err" : "warn"}">${escHtml(consent)}</span>`,
      `<span>${escHtml(tSync("ov.banks.budget", { used: b.budget_used_today ?? 0, limit: b.budget_limit ?? 4 }))}</span>`,
    ];
    if (blocked) {
      facts.push(`<span class="warn">${escHtml(tSync("ov.banks.blocked", { date: fmtDate(b.blocked_until, true) }))}</span>`);
    }
    if (b.last_success) {
      facts.push(`<span>${escHtml(tSync("ov.banks.last_success", { date: fmtDate(b.last_success, true) }))}</span>`);
    }
    if (b.last_error) {
      facts.push(`<span class="err">${escHtml(tSync("ov.banks.last_error", { error: b.last_error }))}</span>`);
    }
    const renew = state === "ok"
      ? ""
      : `<a class="btn btn-p" data-nav href="${window._fd.INTEGRATION_PATH}">${tSync("ov.banks.renew")}</a>`;
    return `
<div class="row">
  <div class="grow">
    <div class="name">${escHtml(b.title || "Bank")} <span class="badge ${state}">${escHtml(badge)}</span></div>
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
        ? ` <span class="badge">${tSync("ov.tx.pending")}</span>` : "";
      return `<tr>
  <td class="date">${escHtml(fmtDate(tx.date))}</td>
  <td><div class="p">${escHtml(party)}${pending}</div><div class="sub">${escHtml(tx.description)}</div></td>
  <td class="acc sub">${escHtml(tx.account_name)}</td>
  <td class="r ${n < 0 ? "neg" : "pos"}">${escHtml(fmtAmt(tx))}</td>
</tr>`;
    });
    const from = t.offset + 1;
    const to = t.offset + t.items.length;
    list.innerHTML = `
<table>
  <thead><tr><th>${tSync("ov.tx.col_date")}</th><th>${tSync("ov.tx.col_party")}</th>
  <th class="acc">${tSync("ov.tx.col_account")}</th><th class="r">${tSync("ov.tx.col_amount")}</th></tr></thead>
  <tbody>${body.join("")}</tbody>
</table>
<div class="pager">
  <span class="muted">${escHtml(tSync("ov.tx.range", { from, to, total: t.total }))}</span>
  <span>
    <button class="btn" id="prev" ${t.offset <= 0 ? "disabled" : ""}>${tSync("ov.tx.prev")}</button>
    <button class="btn" id="next" ${to >= t.total ? "disabled" : ""}>${tSync("ov.tx.next")}</button>
  </span>
</div>`;
    list.querySelector("#prev").addEventListener("click", () => this._loadTransactions(Math.max(0, t.offset - PAGE_SIZE)));
    list.querySelector("#next").addEventListener("click", () => this._loadTransactions(t.offset + PAGE_SIZE));
  }
}

window._fd.defineOnce("fd-overview", FdOverview);
