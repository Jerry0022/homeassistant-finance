/**
 * Finance Dashboard — Home screen (Heute · Woche · Zyklus · Jahr)
 *
 * The panel's first view. One request per horizon/view against the cache-only
 * GET finance_dashboard/home endpoint (never a live bank fetch).
 *
 * Navigation (same on mobile and desktop):
 *   - top: freshness icon · Eilmeldung pill · star with open-question badge
 *   - segment control Heute · Woche · Zyklus · Jahr, also swipeable
 *     (pointer events + arrow keys, no hint texts)
 *   - bottom: oval Person <-> Haushalt pill toggle
 * Desktop (@container >= 760px) adds a side column with pot management
 * (create, edit, delete, rule-based "new pot" suggestions) marked purple.
 *
 * Events out (composed, bubbling):
 *   fd-categorize-requested   star tapped -> shell opens the categorise flow
 *   fd-demo-toggle            "Start demo" on the not-configured screen
 *
 * Properties in: hass, demo (boolean, demo data via ?demo=1).
 */

const DOMAIN = "finance_dashboard";
const HORIZONS = ["today", "week", "cycle", "year"];
const DISMISS_KEY = "fd_home_dismissed_suggestions";
const SUGGEST_SKIP = new Set(["income", "transfers", "other"]);

const CSS = `
:host { display: block; }
.root { container: home / inline-size; position: relative; color: var(--fd-t1); font-size: 13px; line-height: 1.4; }
.top { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 8px; padding: 6px 4px 10px; }
.top > * { min-width: 0; }
button { font: inherit; color: inherit; cursor: pointer; }
.ib { display: inline-flex; align-items: center; justify-content: center; min-width: var(--fd-touch); min-height: var(--fd-touch); border: 0; background: transparent; border-radius: 50%; padding: 0; }
.fresh { justify-self: start; }
.fresh i { display: flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 50%; font-style: normal; font-size: 13px; background: var(--fd-ok-bg); color: var(--fd-ok); }
.fresh.stale i { background: var(--fd-near-bg); color: var(--fd-near); }
.fresh.error i { background: var(--fd-over-bg); color: var(--fd-over); }
.pill { display: inline-flex; align-items: center; gap: 8px; min-height: var(--fd-touch); max-width: 100%; padding: 6px 14px 6px 10px; border: 1px solid var(--fd-line); border-left: 4px solid var(--fd-attn); border-radius: var(--fd-r-pill); background: var(--fd-card); box-shadow: var(--fd-sh2); font-size: 12.5px; font-weight: 500; }
.pill.info { border-left-color: var(--fd-a500); }
.pill i { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--fd-attn); box-shadow: 0 0 0 3px color-mix(in srgb, var(--fd-attn) 24%, transparent); }
.pill span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ttl { font-size: 16px; font-weight: 500; text-align: center; }
.ask { justify-self: end; position: relative; width: var(--fd-touch); height: var(--fd-touch); }
.ask .ring { display: flex; align-items: center; justify-content: center; width: 36px; height: 36px; padding: 3px; border-radius: 50%; background: conic-gradient(var(--fd-gold) 0 var(--p, 0%), var(--fd-sunk) 0); }
.ask .ring span { display: flex; align-items: center; justify-content: center; width: 100%; height: 100%; border-radius: 50%; font-size: 15px; background: var(--fd-card); color: var(--fd-gold); }
.ask b { position: absolute; top: 0; right: 0; min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px; font-size: 11px; line-height: 18px; text-align: center; background: var(--fd-a700); color: #fff; }
.panel { margin: 0 0 12px; padding: 8px; border-radius: var(--fd-r-card); background: var(--fd-card); box-shadow: var(--fd-sh2); }
.alert { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 10px; border-left: 4px solid var(--fd-a500); border-radius: 8px; }
.alert.warn { border-left-color: var(--fd-attn); }
.alert + .alert { margin-top: 6px; }
.fnote { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin: 0 0 12px; padding: 8px 12px; border-radius: 10px; background: var(--fd-sunk); color: var(--fd-t2); font-size: 12px; }
.seg { display: flex; gap: 2px; margin: 0 0 12px; border-bottom: 1px solid var(--fd-line); }
.seg button { flex: 1; min-height: var(--fd-touch); border: 0; border-bottom: 3px solid transparent; margin-bottom: -1px; background: transparent; color: var(--fd-t2); font-size: 14px; }
.seg button[aria-selected="true"] { color: var(--fd-a900); font-weight: 500; border-bottom-color: var(--fd-a500); }
.layout { display: block; }
.side { display: none; }
.main { touch-action: pan-y; min-height: 40vh; padding-bottom: 76px; }
.main.slide-l { animation: slidel .2s ease-out; }
.main.slide-r { animation: slider .2s ease-out; }
@keyframes slidel { from { opacity: 0; transform: translateX(24px); } }
@keyframes slider { from { opacity: 0; transform: translateX(-24px); } }
.card { margin: 0 0 12px; padding: 12px 14px; border-radius: var(--fd-r-card); background: var(--fd-card); box-shadow: var(--fd-sh1); }
.h { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin: 0 0 8px; font-size: 14px; font-weight: 500; }
.h .sub { font-size: 11.5px; font-weight: 400; color: var(--fd-t2); }
.muted { color: var(--fd-t2); font-size: 11.5px; }
.st-ok { --c: var(--fd-ok); --cbg: var(--fd-ok-bg); --cfg: color-mix(in srgb, var(--fd-ok) 72%, var(--fd-t1)); }
.st-near { --c: var(--fd-near); --cbg: var(--fd-near-bg); --cfg: color-mix(in srgb, var(--fd-near) 72%, var(--fd-t1)); }
.st-over { --c: var(--fd-over); --cbg: var(--fd-over-bg); --cfg: color-mix(in srgb, var(--fd-over) 72%, var(--fd-t1)); }
.chip { display: inline-flex; align-items: center; gap: 4px; padding: 1px 9px; border-radius: var(--fd-r-pill); font-size: 11.5px; font-weight: 500; white-space: nowrap; background: var(--cbg); color: var(--cfg); }
.big { font-size: 40px; font-weight: 500; line-height: 1.05; color: var(--cfg, var(--fd-t1)); }
.hero { display: flex; align-items: flex-end; justify-content: space-between; gap: 10px; }
.cap { margin-top: 4px; font-size: 12.5px; color: var(--fd-t2); }
.meter { position: relative; height: 12px; margin: 14px 0 6px; border-radius: 6px; background: var(--fd-sunk); }
.meter > i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 6px; background: var(--c); }
.meter > b { position: absolute; top: -6px; width: 4px; height: 24px; margin-left: -2px; border-radius: 2px; background: var(--fd-t1); box-shadow: 0 0 0 2px var(--fd-card); }
.meter > b span { position: absolute; bottom: 26px; left: 50%; transform: translateX(-50%); font-size: 11px; font-weight: 500; white-space: nowrap; }
.pot { display: grid; grid-template-columns: 4px 1fr auto; align-items: center; column-gap: 10px; padding: 9px 0; }
.pot + .pot { border-top: 1px solid var(--fd-line); }
.pot > i { align-self: stretch; border-radius: 2px; background: var(--c); }
.pot > span { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.pot > span b { font-weight: 500; overflow: hidden; text-overflow: ellipsis; }
.pot > em { font-style: normal; font-size: 18px; font-weight: 500; color: var(--cfg); white-space: nowrap; }
.add { width: var(--fd-touch); height: var(--fd-touch); margin: -10px -10px -10px 0; border: 0; border-radius: 50%; background: transparent; color: var(--fd-t2); font-size: 22px; line-height: 1; }
.add:hover { background: var(--fd-sunk); color: var(--fd-a700); }
.band { margin: -12px -14px 12px; padding: 14px; border-radius: var(--fd-r-card) var(--fd-r-card) 0 0; background: var(--cbg); }
.band .big { font-size: 30px; }
.carry { display: flex; align-items: center; gap: 10px; margin: 0 0 12px; padding: 8px 10px; border-radius: 10px; background: var(--fd-a50); color: var(--fd-a900); font-size: 12.5px; }
.carry b { flex: none; padding: 3px 9px; border-radius: var(--fd-r-pill); background: var(--fd-card); }
.chart { position: relative; height: 130px; border-radius: 10px; background: var(--fd-sunk); }
.chart svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.days { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; margin-top: 6px; text-align: center; font-size: 11px; color: var(--fd-t2); }
.days b { display: block; font-weight: 500; color: var(--fd-t1); }
.days .today { color: var(--fd-a900); font-weight: 600; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 8px; font-size: 11px; color: var(--fd-t2); }
.legend i { display: inline-block; width: 14px; height: 8px; margin-right: 4px; border-radius: 2px; background: var(--fd-ok); vertical-align: 0; }
.legend i.l1 { height: 0; border-top: 2px solid var(--fd-a900); border-radius: 0; background: none; vertical-align: 3px; }
.legend i.l2 { height: 0; border-top: 1px dashed var(--fd-t2); border-radius: 0; background: none; vertical-align: 3px; }
.tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 12px; }
.tile { padding: 8px 10px; border-radius: 10px; background: var(--fd-sunk); }
.tile span { display: block; font-size: 11px; color: var(--fd-t2); }
.tile b { display: block; font-size: 17px; font-weight: 500; }
.row { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 7px 0; }
.row + .row { border-top: 1px solid var(--fd-line); }
.row > span:first-child { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.row .amt { white-space: nowrap; }
.tag { margin-left: 6px; padding: 0 7px; border: 1px dashed var(--fd-t3); border-radius: var(--fd-r-pill); font-size: 10.5px; color: var(--fd-t2); }
.more { display: flex; align-items: center; width: 100%; min-height: var(--fd-touch); margin-top: 2px; padding: 0; border: 0; border-top: 1px solid var(--fd-line); background: transparent; color: var(--fd-a700); text-align: left; }
.tank { position: relative; height: 96px; margin-top: 10px; border-radius: 12px; background: var(--fd-a50); overflow: hidden; }
.tank > i { position: absolute; left: 0; top: 0; bottom: 0; background: var(--c); opacity: .85; }
.tank > b { position: absolute; top: 0; bottom: 0; width: 0; border-left: 2px dashed var(--fd-a900); }
.tank > b span { position: absolute; top: 6px; left: 6px; padding: 0 7px; border-radius: var(--fd-r-pill); font-size: 10.5px; font-weight: 600; background: var(--fd-card); color: var(--fd-a900); }
.tank > .ta { position: absolute; right: 14px; bottom: 10px; text-align: right; font-size: 28px; font-weight: 500; line-height: 1.05; color: var(--fd-t1); }
.tank > .ta small { display: block; font-size: 11px; font-weight: 400; color: var(--fd-t2); }
.tank > b.r span { left: auto; right: 6px; }
.flip { animation: flipin .28s ease-out; }
@keyframes flipin { from { opacity: 0; transform: rotateY(60deg); } }
.info { flex: none; box-sizing: border-box; min-width: var(--fd-touch); display: inline-flex; align-items: center; justify-content: center; width: var(--fd-touch); height: var(--fd-touch); margin: -10px 0 -10px -6px; border: 0; border-radius: 50%; background: transparent; color: var(--fd-a700); font-size: 15px; }
.verdict { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; }
.verdict .chip { padding: 3px 12px; font-size: 14px; }
.know { display: flex; gap: 10px; align-items: flex-start; border-left: 4px solid var(--fd-a500); }
.know b { display: block; margin-bottom: 2px; font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase; color: var(--fd-a700); }
.cyc { display: grid; grid-template-columns: repeat(auto-fill, minmax(44px, 1fr)); gap: 4px; }
.cyc span { display: flex; align-items: flex-end; justify-content: center; height: 36px; padding-bottom: 2px; border-radius: 6px; font-size: 9px; color: #fff; background: var(--c, var(--fd-sunk)); }
.cyc span.run { background: repeating-linear-gradient(135deg, var(--fd-near) 0 4px, color-mix(in srgb, var(--fd-near) 60%, #fff) 4px 8px); }
.cyc span.fut { background: var(--fd-sunk); color: var(--fd-t3); }
.cmp { height: 8px; margin: 4px 0; border-radius: 4px; background: var(--fd-sunk); overflow: hidden; }
.cmp i { display: block; height: 100%; background: var(--fd-a500); }
.cmp.prev i { background: var(--fd-t3); }
.entry { display: flex; align-items: center; gap: 10px; width: 100%; min-height: var(--fd-touch); margin: 0 0 12px; padding: 10px 14px; border: 0; border-radius: var(--fd-r-card); background: var(--fd-card); box-shadow: var(--fd-sh1); text-align: left; }
.entry > i { flex: none; display: flex; align-items: center; justify-content: center; width: 34px; height: 34px; border-radius: 10px; font-style: normal; background: var(--fd-a50); color: var(--fd-a700); }
.entry > span { flex: 1; display: flex; flex-direction: column; }
.entry[aria-disabled="true"] { cursor: default; opacity: .8; }
.dsk { border: 1px dashed var(--fd-desktop); background: var(--fd-desktop-bg); color: var(--fd-desktop); }
.dtag { display: inline-flex; align-items: center; gap: 4px; padding: 1px 8px; border-radius: var(--fd-r-pill); font-size: 10.5px; font-weight: 500; background: var(--fd-desktop-bg); color: var(--fd-desktop); }
.dtag::before { content: "\\25C6"; font-size: 8px; }
.btn { min-height: var(--fd-touch); padding: 0 16px; border: 1px solid transparent; border-radius: var(--fd-r-pill); background: var(--fd-a700); color: #fff; font-weight: 500; }
.btn.ghost { background: transparent; color: var(--fd-a700); border-color: var(--fd-a100); }
.btn.sm { min-height: 36px; padding: 0 12px; font-size: 12px; }
.btn.danger { background: transparent; color: var(--fd-over); border-color: var(--fd-over-bg); }
.btn.dsk { border-style: dashed; }
.setup h3 { margin: 0 0 6px; font-size: 16px; font-weight: 600; }
.setup .acts { margin-top: 12px; }
.nav[hidden] { display: none; }
.nav { position: sticky; bottom: 12px; z-index: 5; display: flex; justify-content: center; pointer-events: none; }
.toggle { pointer-events: auto; display: inline-flex; gap: 2px; padding: 4px; border-radius: var(--fd-r-pill); background: var(--fd-card); box-shadow: var(--fd-sh2); border: 1px solid var(--fd-line); }
.toggle button { min-height: var(--fd-touch); min-width: 96px; padding: 0 18px; border: 0; border-radius: var(--fd-r-pill); background: transparent; color: var(--fd-t2); font-weight: 500; }
.toggle button[aria-checked="true"] { background: var(--pc, var(--fd-a700)); color: #fff; }
.toggle button:disabled { opacity: .4; cursor: not-allowed; }
.msg { padding: 32px 12px; text-align: center; color: var(--fd-t2); }
.msg .btn { margin-top: 12px; }
.live { position: fixed; left: 50%; bottom: 80px; transform: translateX(-50%); z-index: 40; padding: 8px 14px; border-radius: var(--fd-r-pill); background: var(--fd-card); border: 1px solid var(--fd-line); box-shadow: var(--fd-sh2); }
.scrim { position: fixed; inset: 0; z-index: 50; display: flex; align-items: flex-end; justify-content: center; background: rgba(0,0,0,.4); }
.sheet { width: min(480px, 100%); max-height: 90dvh; overflow: auto; padding: 16px; border-radius: 18px 18px 0 0; background: var(--fd-card); box-shadow: var(--fd-sh2); }
.sheet label, .sheet .lbl { display: block; margin: 12px 0 4px; font-size: 12px; color: var(--fd-t2); }
.sheet input[type=text], .sheet input[type=number] { box-sizing: border-box; width: 100%; min-height: var(--fd-touch); padding: 0 12px; border: 1px solid var(--fd-line); border-radius: 10px; background: var(--fd-page); color: var(--fd-t1); font: inherit; }
.opts { display: flex; flex-wrap: wrap; gap: 6px; }
.opts button { min-height: 40px; padding: 0 14px; border: 1px solid var(--fd-line); border-radius: var(--fd-r-pill); background: transparent; }
.opts button[aria-pressed="true"], .opts button[aria-checked="true"] { background: var(--fd-a50); border-color: var(--fd-a500); color: var(--fd-a900); font-weight: 500; }
.acts { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.err { margin-top: 8px; color: var(--fd-over); font-size: 12px; }
.mg { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 0; }
.mg + .mg { border-top: 1px solid var(--fd-line); }
.mg > span { min-width: 0; display: flex; flex-direction: column; }
.mg .btns { display: flex; gap: 6px; flex: none; }
.sug { padding: 8px 10px; border: 1px dashed var(--fd-desktop); border-radius: 10px; background: var(--fd-desktop-bg); }
.sug + .sug { margin-top: 6px; }
@container home (min-width: 760px) {
  .layout { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(280px, 1fr); gap: 16px; align-items: start; }
  .side { display: block; }
  .main { padding-bottom: 76px; }
  .scrim { align-items: center; }
  .sheet { border-radius: 18px; }
  .top .fresh span.t { display: inline; }
}
.fresh span.t { display: none; margin-left: 6px; font-size: 12px; color: var(--fd-t2); }
`;

class FdHome extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._demo = false;
    this._horizon = "today";
    this._view = "person";
    this._data = null;
    this._err = null; // "nc" | "err" | null
    this._busy = false;
    this._seq = 0;
    this._flipped = false;
    this._moreNext = false;
    this._alertsOpen = false;
    this._freshOpen = false;
    this._sheet = null;
    this._rendered = false;
    this._toastTimer = null;
  }

  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    if (first) {
      this._renderShell();
      this._load();
    }
  }

  get demo() { return this._demo; }
  set demo(v) {
    v = !!v;
    if (v === this._demo) return;
    this._demo = v;
    if (this._hass) this._load();
  }

  reload() { return this._load(); }

  // ---- data -------------------------------------------------------------
  async _load(dir) {
    if (!this._hass) return;
    const seq = ++this._seq;
    this._busy = true;
    const q = `horizon=${this._horizon}&view=${this._view}${this._demo ? "&demo=1" : ""}`;
    try {
      const d = await this._hass.callApi("GET", `${DOMAIN}/home?${q}`);
      if (seq !== this._seq) return;
      this._data = d;
      this._err = null;
      if (d && d.view && d.view !== this._view) this._view = d.view;
    } catch (e) {
      if (seq !== this._seq) return;
      this._err = e && e.status_code === 404 ? "nc" : "err";
    }
    this._busy = false;
    this._paint(dir);
  }

  _setHorizon(h, dir) {
    if (!HORIZONS.includes(h) || h === this._horizon) return;
    const from = HORIZONS.indexOf(this._horizon);
    this._horizon = h;
    this._flipped = false;
    this._moreNext = false;
    this._load(HORIZONS.indexOf(h) > from ? "l" : "r");
    this._paint(dir || (HORIZONS.indexOf(h) > from ? "l" : "r"));
  }

  _step(delta) {
    const i = HORIZONS.indexOf(this._horizon) + delta;
    if (i >= 0 && i < HORIZONS.length) this._setHorizon(HORIZONS[i]);
  }

  _setView(v) {
    if (v === this._view) return;
    this._view = v;
    this._load();
    this._paint();
  }

  // ---- helpers ----------------------------------------------------------
  get _t() { return window._fd.tSync; }
  _e(s) { return window._fd.escHtml(s); }
  _m(v, dec) {
    return new Intl.NumberFormat("de-DE", {
      style: "currency", currency: "EUR",
      minimumFractionDigits: dec ? 2 : 0, maximumFractionDigits: dec ? 2 : 0,
    }).format(v || 0);
  }
  _lang() { return (this._hass && this._hass.language) || navigator.language || "de"; }
  _day(iso) {
    const d = new Date(`${iso}T12:00:00`);
    return isNaN(d) ? "" : d.toLocaleDateString(this._lang(), { day: "numeric", month: "short" });
  }
  _wd(iso) {
    const d = new Date(`${iso}T12:00:00`);
    return isNaN(d) ? "" : d.toLocaleDateString(this._lang(), { weekday: "short" });
  }
  _cls(s) { return s === "over" ? "st-over" : s === "knapp" ? "st-near" : "st-ok"; }
  _statusOf(spent, linear) {
    if (spent <= linear + 0.005) return "good";
    return spent <= linear * 1.1 ? "knapp" : "over";
  }
  _chip(s) { return `<span class="chip ${this._cls(s)}">${this._t("home.status." + (s === "good" || !s ? "good" : s))}</span>`; }
  _toast(msg) {
    const el = this.shadowRoot.getElementById("live");
    if (!el) return;
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => { el.hidden = true; }, 3200);
  }

  // ---- shell ------------------------------------------------------------
  _renderShell() {
    const sh = this.shadowRoot;
    sh.innerHTML = `<style>${window._fd.SHARED_CSS}${CSS}</style>
<div class="root">
  <div id="top"></div>
  <div id="panels"></div>
  <div class="seg" id="seg" role="tablist" aria-label="${this._t("home.h.label")}"></div>
  <div class="layout">
    <div class="main" id="main" role="tabpanel" aria-live="polite"></div>
    <aside class="side" id="side"></aside>
  </div>
  <div class="nav"><div class="toggle" id="toggle" role="radiogroup" aria-label="${this._t("home.view.label")}"></div></div>
  <div class="live" id="live" role="status" hidden></div>
  <div id="sheet"></div>
</div>`;
    sh.addEventListener("click", (e) => this._onClick(e));
    sh.addEventListener("keydown", (e) => this._onKey(e));
    const main = sh.getElementById("main");
    let sx = 0, sy = 0, down = false;
    main.addEventListener("pointerdown", (e) => {
      if (e.target.closest("button, input, a")) return;
      down = true; sx = e.clientX; sy = e.clientY;
    });
    main.addEventListener("pointerup", (e) => {
      if (!down) return;
      down = false;
      const dx = e.clientX - sx, dy = e.clientY - sy;
      if (Math.abs(dx) > 56 && Math.abs(dx) > Math.abs(dy) * 1.6) this._step(dx < 0 ? 1 : -1);
    });
    main.addEventListener("pointercancel", () => { down = false; });
    this._rendered = true;
    this._paint();
  }

  _onKey(e) {
    if (e.key === "Escape" && this._sheet) { this._closeSheet(); return; }
    if (this._sheet) return;
    if ((e.key === "ArrowRight" || e.key === "ArrowLeft") && e.target.closest && e.target.closest("#seg")) {
      this._step(e.key === "ArrowRight" ? 1 : -1);
      const b = this.shadowRoot.querySelector(`#seg [data-h="${this._horizon}"]`);
      if (b) b.focus();
    }
  }

  _paint(dir) {
    if (!this._rendered) return;
    const sh = this.shadowRoot;
    const d = this._data;
    sh.getElementById("top").innerHTML = this._topHtml();
    sh.getElementById("panels").innerHTML = this._panelsHtml();
    sh.getElementById("seg").innerHTML = HORIZONS.map((h) => {
      const on = h === this._horizon;
      return `<button role="tab" data-h="${h}" aria-selected="${on}" tabindex="${on ? 0 : -1}">${this._t("home.h." + h)}</button>`;
    }).join("");
    const main = sh.getElementById("main");
    main.classList.remove("slide-l", "slide-r");
    if (dir) { void main.offsetWidth; main.classList.add("slide-" + dir); }
    let body;
    if (this._err === "nc" && !d) body = this._notConfigured();
    else if (this._err && !d) body = `<div class="msg">${this._t("home.error")}<br><button class="btn" data-act="retry">${this._t("home.retry")}</button></div>`;
    else if (!d) body = `<div class="msg">${this._t("home.loading")}</div>`;
    else body = this._body(d);
    main.innerHTML = body;
    sh.getElementById("side").innerHTML = d ? this._sideHtml(d) : "";
    const hasPerson = !!(d && d.person);
    // Only a user mapped to a person has two views; otherwise the pill would offer nothing.
    sh.getElementById("toggle").parentElement.hidden = !!d && !hasPerson;
    const pName = d && d.person ? d.person.name : this._t("home.view.person");
    sh.getElementById("toggle").innerHTML = `
      <button role="radio" data-v="person" aria-checked="${this._view === "person"}" style="--pc:var(--fd-person-a)" ${hasPerson || !d ? "" : "disabled"}>${this._e(pName)}</button>
      <button role="radio" data-v="household" aria-checked="${this._view === "household"}" style="--pc:var(--fd-household)">${this._t("home.view.household")}</button>`;
  }

  _notConfigured() {
    return `<div class="msg">${this._t("home.not_configured")}<br><button class="btn" data-act="demo">${this._t("home.demo")}</button></div>`;
  }

  // ---- top bar ----------------------------------------------------------
  _topHtml() {
    const d = this._data || {};
    const fr = d.freshness || { status: "fresh" };
    const icon = fr.status === "error" ? "!" : fr.status === "stale" ? "↻" : "✓";
    const flabel = this._t("home.fresh." + (fr.status || "fresh"));
    const alerts = d.alerts || [];
    const worst = alerts.find((a) => a.severity === "warn") || alerts[0];
    const q = d.questions_open || 0;
    const center = alerts.length
      ? `<button class="pill ${worst.severity === "warn" ? "" : "info"}" data-act="alerts" aria-expanded="${this._alertsOpen}" aria-label="${this._t("home.alert.open")}"><i></i><span>${this._e(this._alertTitle(worst))}</span>${alerts.length > 1 ? `<span class="muted">+${alerts.length - 1}</span>` : ""}</button>`
      : `<div class="ttl">Finance</div>`;
    return `<div class="top">
  <button class="ib fresh ${fr.status || ""}" data-act="fresh" data-tip="${this._e(flabel)}" aria-label="${this._e(flabel)}" aria-expanded="${this._freshOpen}"><i>${icon}</i><span class="t">${this._e(flabel)}</span></button>
  ${center}
  <button class="ib ask" data-act="ask" data-tip="${this._e(q ? this._t("home.star", { n: q }) : this._t("home.star.none"))}" aria-label="${this._e(q ? this._t("home.star", { n: q }) : this._t("home.star.none"))}">
    <span class="ring" style="--p:${q ? 86 : 100}%"><span>★</span></span>${q ? `<b>${Math.min(q, 10)}</b>` : ""}</button>
</div>`;
  }

  _alertTitle(a) {
    const key = "home.alert." + a.kind;
    const s = this._t(key, { bank: a.title || "" });
    return s === key ? (a.title || "") : s;
  }

  _panelsHtml() {
    const d = this._data || {};
    let h = "";
    if (this._freshOpen && d.freshness) {
      const when = d.freshness.as_of ? new Date(d.freshness.as_of).toLocaleString(this._lang(), { dateStyle: "short", timeStyle: "short" }) : "";
      h += `<div class="fnote">${this._t("home.fresh.as_of", { time: this._e(when) })} <button class="btn" data-act="refresh">${this._t("home.fresh.refresh")}</button></div>`;
    }
    if (this._alertsOpen && (d.alerts || []).length) {
      h += `<div class="panel" role="region" aria-label="${this._t("home.alert.open")}">${d.alerts.map((a) => `
        <div class="alert ${a.severity}"><span>${this._e(this._alertTitle(a))}</span>
        <span><button class="btn sm" data-act="renew">${this._t("home.alert.renew")}</button></span></div>`).join("")}
        <div class="acts"><button class="btn ghost sm" data-act="alerts">${this._t("home.alert.close")}</button></div></div>`;
    }
    return h;
  }

  // ---- bodies -----------------------------------------------------------
  _body(d) {
    // Without a budget the figures are all 0 € and "passt" would be a false reading.
    if (this._horizon !== "year" && this._budgetTotals(d).budget <= 0) return this._setupCard(d);
    switch (this._horizon) {
      case "today": return this._today(d);
      case "week": return this._week(d);
      case "cycle": return this._cycle(d);
      default: return this._year(d);
    }
  }

  /** Empty state: name the one step that makes this screen meaningful. */
  _setupCard(d) {
    const st = d.setup || {};
    const assign = st.persons === 0 || (st.accounts_total || 0) > (st.accounts_assigned || 0);
    const key = assign ? "assign" : "pots";
    const act = assign ? `<button class="btn" data-act="settings">${this._t("home.setup.assign_cta")}</button>`
      : `<button class="btn" data-act="addpot">+ ${this._t("home.pot.new")}</button>`;
    return `<section class="card setup"><h3>${this._t("home.setup." + key + "_title")}</h3>
  <p class="muted">${this._t("home.setup." + key + "_body")}</p><div class="acts">${act}</div></section>`;
  }

  _budgetTotals(d) {
    const pots = d.pots || [], pers = d.persons || [];
    const budget = pots.reduce((s, p) => s + (p.cycle_budget || 0), 0) + pers.reduce((s, p) => s + (p.budget || 0), 0);
    const spent = pots.reduce((s, p) => s + (p.spent || 0), 0) + pers.reduce((s, p) => s + (p.spent || 0), 0);
    return { budget, spent };
  }

  _today(d) {
    const c = this._cls(d.status);
    const t = d.today || {};
    const { budget } = this._budgetTotals(d);
    const cy = d.cycle || { days: 1, day: 1 };
    const left = Math.max(0, d.remaining || 0);
    const pctFill = budget > 0 ? Math.min(100, (left / budget) * 100) : 0;
    const days = t.daily_budget > 0 ? Math.floor(left / t.daily_budget) : null;
    return `<section class="card ${c}">
  <div class="hero"><div><div class="big">${this._m(d.remaining, false)}</div><div class="cap">${this._t("home.today.remaining")}</div></div>${this._chip(d.status)}</div>
  ${budget > 0 ? `<div class="meter" role="img" aria-label="${this._e(this._t("home.today.bar"))}: ${this._m(left, false)}">
    <i style="width:${pctFill.toFixed(1)}%"></i></div>
    <div class="muted">${this._t("home.today.bar")}</div>` : ""}
  <div class="tiles" style="grid-template-columns:1fr 1fr">
    <div class="tile"><span>${this._t("home.today.spent")}</span><b>${this._m(t.spent, true)}</b></div>
    <div class="tile"><span>${days !== null ? this._t("home.today.days", { n: days }) : this._t("home.week.per_day")}</span><b>${this._t("home.today.per_day", { amount: this._m(t.daily_budget, true) })}</b></div>
  </div></section>${this._potsCard(d)}`;
  }

  _potRows(pots) {
    return pots.map((p) => `<div class="pot ${this._cls(p.status)}"><i></i>
      <span><b>${this._e(p.name)}</b><small class="muted">${this._t("home.pots.per_day", { amount: this._m(p.per_day, true) })}</small></span>
      <em>${this._m(p.balance, false)}</em></div>`).join("");
  }

  _potsCard(d) {
    const hh = d.view === "household";
    const pots = d.pots || [];
    const persons = hh ? (d.persons || []) : [];
    const personRows = persons.map((p) => `<div class="pot ${this._cls(p.status)}"><i></i>
      <span><b>${this._e(p.name)}</b><small class="muted">${this._t("home.persons.left")}</small></span>
      <em>${this._m(p.balance, false)}</em></div>`).join("");
    return `<section class="card"><div class="h"><span>${this._t(hh ? "home.pots.household" : "home.pots.person")}</span>
      <button class="add" data-act="addpot" data-tip="${this._t("home.pots.add")}" aria-label="${this._t("home.pots.add")}">+</button></div>
      ${pots.length || persons.length ? this._potRows(pots) + (persons.length ? `<div class="h" style="margin-top:10px"><span class="muted">${this._t("home.persons.title")}</span></div>${personRows}` : "")
        : `<div class="muted">${this._t("home.pots.empty")}</div>`}</section>`;
  }

  _upcoming(items, title, sum) {
    const rows = (items || []).map((i) => `<div class="row"><span>${this._e(i.label)}${i.pending ? `<span class="tag">${this._t("home.pending")}</span>` : ""}
      <small class="muted"> ${this._day(i.date)}</small></span><span class="amt">${this._m(i.amount, true)}</span></div>`).join("");
    return `<section class="card"><div class="h"><span>${title}</span>${sum !== undefined ? `<span class="sub">${this._m(sum, true)}</span>` : ""}</div>
      ${rows || `<div class="muted">${this._t("home.upcoming.none")}</div>`}</section>`;
  }

  _week(d) {
    const w = d.week;
    if (!w) return "";
    const days = w.days || [];
    const lin = w.linear_line || [], zero = w.zero_carry_line || [];
    let acc = 0;
    const cum = days.map((x) => (acc += x.actual || 0));
    const tIdx = Math.max(0, days.findIndex((x) => x.today));
    const st = this._statusOf(cum[tIdx] || 0, lin[tIdx] || 0);
    const cc = this._cls(st);
    const ymax = Math.max(1, ...lin, ...zero, ...cum) * 1.12;
    const X = (i) => i * 100 + 50, Y = (v) => 140 - (v / ymax) * 132;
    const bars = days.map((x, i) => {
      if (x.future) return "";
      const s = this._statusOf(cum[i], lin[i] || 0);
      const col = s === "over" ? "var(--fd-over)" : s === "knapp" ? "var(--fd-near)" : "var(--fd-ok)";
      const h = Math.max(0, (cum[i] / ymax) * 132);
      return `<rect x="${i * 100 + 18}" width="64" y="${140 - h}" height="${h}" rx="4" fill="${col}"/>`;
    }).join("");
    const pts = (a) => a.map((v, i) => `${X(i)},${Y(v)}`).join(" ");
    const carry = w.carry_over || 0;
    return `<section class="card ${cc}"><div class="band"><div class="big">${this._m(w.remaining, false)}</div>
      <div class="cap">${this._t("home.week.left")} ${this._chip(st)}</div></div>
    ${Math.abs(carry) >= 0.5 ? `<div class="carry"><b>${carry > 0 ? "+" : "−"}${this._m(Math.abs(carry), false)}</b><span>${this._t(carry > 0 ? "home.week.carry_plus" : "home.week.carry_minus")}</span></div>` : ""}
    <div class="chart"><svg viewBox="0 0 700 140" preserveAspectRatio="none" role="img" aria-label="${this._t("home.week.chart")}">
      ${bars}<polyline points="${pts(zero)}" fill="none" stroke="var(--fd-t2)" stroke-width="1.2" stroke-dasharray="5 5" vector-effect="non-scaling-stroke"/>
      <polyline points="${pts(lin)}" fill="none" stroke="var(--fd-a900)" stroke-width="2.2" vector-effect="non-scaling-stroke"/></svg></div>
    <div class="days">${days.map((x) => `<div class="${x.today ? "today" : ""}">${this._wd(x.date)}<b>${x.future || !x.in_cycle ? "·" : this._m(x.actual, false)}</b></div>`).join("")}</div>
    <div class="legend"><span><i></i>${this._t("home.week.legend_spent")}</span><span><i class="l1"></i>${this._t("home.week.legend_soll")}</span><span><i class="l2"></i>${this._t("home.week.legend_zero")}</span></div>
    <div class="tiles"><div class="tile"><span>${this._t("home.week.spent")}</span><b>${this._m(w.spent, false)}</b></div>
      <div class="tile"><span>${this._t("home.week.per_day")}</span><b>${this._m(w.daily_budget, false)}</b></div>
      <div class="tile"><span>${this._t("home.week.budget")}</span><b>${this._m(w.week_budget, false)}</b></div></div></section>
    ${this._upcoming((w.upcoming || {}).items, this._t("home.week.upcoming"), (w.upcoming || {}).sum)}`;
  }

  _cycleBlock(d) {
    const cy = d.cycle || {};
    const range = `${this._day(cy.start)} – ${this._day(cy.end)}`;
    const head = (extra) => `<div class="h"><span>${this._t("home.cycle.title")} ${this._e(range)}<button class="info" data-act="flip" data-tip="${this._e(this._flipped ? this._t("home.cycle.back") : this._t("home.cycle.info"))}" aria-label="${this._e(this._flipped ? this._t("home.cycle.back") : this._t("home.cycle.info"))}" aria-pressed="${this._flipped}">${this._flipped ? "×" : "ⓘ"}</button></span><span class="sub">${extra}</span></div>`;
    if (this._flipped) {
      const rule = this._t(`home.cycle.rule.${cy.rule || "calendar_fallback"}`, { name: this._e(cy.anchor || "") });
      return `<section class="card flip">${head(this._t("home.cycle.day", { n: cy.day, total: cy.days }))}<p style="margin:6px 0 0">${rule}</p></section>`;
    }
    const { budget, spent } = this._budgetTotals(d);
    const frac = budget > 0 ? Math.min(1, spent / budget) : 0;
    const soll = cy.days > 0 ? Math.min(1, cy.day / cy.days) : 0;
    const delta = budget * soll - spent;
    const left = Math.max(1, (cy.days || 1) - (cy.day || 1) + 1);
    const verdictKey = d.status === "over" ? "over" : d.status === "knapp" ? "knapp" : "good";
    return `<section class="card ${this._cls(d.status)} flip">${head(this._t("home.cycle.day", { n: cy.day, total: cy.days }))}
      <div class="verdict"><span class="chip">${this._t("home.cycle.verdict." + verdictKey)}</span>
        <span class="muted">${this._t(delta >= 0 ? "home.cycle.ahead" : "home.cycle.behind", { amount: this._m(Math.abs(delta), false) })}</span></div>
      <div class="tank" role="img" aria-label="${this._e(this._t("home.cycle.left"))}: ${this._m(d.remaining, false)}">
        <i style="width:${(frac * 100).toFixed(1)}%"></i><b style="left:${(soll * 100).toFixed(1)}%" aria-hidden="true"></b>
        <div class="ta">${this._m(d.remaining, false)}<small>${this._t("home.cycle.left")}</small></div></div>
      <div class="tiles"><div class="tile"><span>${this._t("home.cycle.budget")}</span><b>${this._m(budget, false)}</b></div>
        <div class="tile"><span>${this._t("home.cycle.spent")}</span><b>${this._m(spent, false)}</b></div>
        <div class="tile"><span>${this._t("home.cycle.per_day")}</span><b>${this._m(Math.max(0, d.remaining) / left, false)}</b></div></div></section>`;
  }

  _fixed(d) {
    if (d.fixed_costs_covered === null || d.fixed_costs_covered === undefined) return "";
    return `<div style="margin:0 0 12px"><span class="chip ${d.fixed_costs_covered ? "st-ok" : "st-near"}">${d.fixed_costs_covered ? "✓ " : ""}${this._t(d.fixed_costs_covered ? "home.cycle.fixed_ok" : "home.cycle.fixed_no")}</span></div>`;
  }

  _dyk(d) {
    const k = d.did_you_know;
    if (!k) return "";
    const p = k.params || {};
    const cat = (window._fd.CAT_LABELS || {})[p.category] || p.category;
    const key = "home.dyk." + k.key;
    let text = this._t(key, { share: Math.round((p.share || 0) * 100), category: cat });
    if (text === key) text = k.text || "";
    return `<section class="card know"><span><b>${this._t("home.dyk.title")}</b>${this._e(text)}</span></section>`;
  }

  _next(d) {
    const all = d.next_all || d.next || [];
    const total = Math.max(d.next_total || 0, all.length);
    const items = this._moreNext ? all : (d.next || []).slice(0, 3);
    const hidden = Math.max(0, total - items.length);
    const toggle = hidden > 0
      ? `<button class="more" data-act="more">${this._t("home.next.more", { n: hidden })}</button>`
      : (this._moreNext && total > 3 ? `<button class="more" data-act="more">${this._t("home.next.less")}</button>` : "");
    return this._upcoming(items, this._t("home.next.title")).replace(/<\/section>$/, toggle + "</section>");
  }

  _reserves(d) {
    const r = d.reserves || [];
    return `<section class="card"><div class="h"><span>${this._t("home.reserves.title")}</span></div>
      ${r.length ? r.map((p) => `<div class="pot st-ok"><i></i><span><b>${this._e(p.name)}</b><small class="muted">${this._t("home.pots.per_day", { amount: this._m(p.per_day, true) })}</small></span><em style="color:var(--fd-t1)">${this._m(p.balance, false)}</em></div>`).join("")
        : `<div class="muted">${this._t("home.reserves.empty")}</div>`}</section>`;
  }

  _cycle(d) {
    return this._cycleBlock(d) + this._fixed(d) + this._dyk(d) + this._next(d) + this._reserves(d);
  }

  _year(d) {
    const y = d.year || {};
    const list = [...new Map((y.cycles || []).map((c) => [c.start, c])).values()].sort((a, b) => a.start.localeCompare(b.start));
    const multiYear = new Set(list.map((c) => c.start.slice(0, 4))).size > 1;
    const cyc = list.map((c) => {
      const cls = c.current ? "run" : (c.status === "good" || c.status === "knapp" || c.status === "over") ? "" : "fut";
      const col = c.status === "over" ? "var(--fd-over)" : c.status === "knapp" ? "var(--fd-near)" : "var(--fd-ok)";
      const lab = new Date(`${c.start}T12:00:00`).toLocaleDateString(this._lang(), multiYear ? { month: "short", year: "2-digit" } : { month: "short" });
      const st = c.status && !cls.includes("fut") ? this._t("home.status." + c.status) : "";
      return `<span class="${cls}" style="--c:${col}" aria-label="${this._e(lab + " " + (c.current ? this._t("home.year.running") : st))}" data-tip="${this._e(lab + (st ? " · " + st : ""))}">${this._e(lab)}</span>`;
    }).join("");
    const v = y.vs_last_year || {};
    let vs;
    if (v.available) {
      const mx = Math.max(v.spent, v.spent_last_year, 1);
      vs = `<div class="row"><span>${this._t("home.year.this")}</span><span class="amt">${this._m(v.spent, false)}</span></div>
        <div class="cmp"><i style="width:${(v.spent / mx) * 100}%"></i></div>
        <div class="row"><span>${this._t("home.year.last")}</span><span class="amt">${this._m(v.spent_last_year, false)}</span></div>
        <div class="cmp prev"><i style="width:${(v.spent_last_year / mx) * 100}%"></i></div>
        <div class="muted">${this._t(v.delta <= 0 ? "home.year.vs_less" : "home.year.vs_more", { amount: this._m(Math.abs(v.delta), false) })}</div>`;
    } else vs = `<div class="muted">${this._t("home.year.vs_na")}</div>`;
    const soon = `<span class="tag">${this._t("home.soon")}</span>`;
    return `<section class="card"><div class="h"><span>${this._t("home.year.title")}</span></div><div class="cyc">${cyc}</div></section>
      <section class="card"><div class="h"><span>${this._t("home.year.vs")}</span></div>${vs}</section>
      <button class="entry" aria-disabled="true"><i>☰</i><span><b>${this._t("home.year.contracts")}${soon}</b><small class="muted">${this._t("home.year.contracts_sub")}</small></span></button>
      <button class="entry" aria-disabled="true"><i>≈</i><span><b>${this._t("home.year.benchmark")}${soon}</b><small class="muted">${this._t("home.year.benchmark_sub")}</small></span></button>
      ${this._dyk(d)}${this._reserves(d)}`;
  }

  // ---- desktop side column ----------------------------------------------
  _allPots(d) {
    return [...(d.pots || []), ...(d.reserves || [])];
  }

  _suggestions(d) {
    let dismissed = [];
    try { dismissed = JSON.parse(localStorage.getItem(DISMISS_KEY) || "[]"); } catch (_) { /* ignore */ }
    const used = new Set(this._allPots(d).flatMap((p) => p.category_keys || []));
    return Object.keys(window._fd.CAT_LABELS || {})
      .filter((k) => !SUGGEST_SKIP.has(k) && !used.has(k) && !dismissed.includes(k))
      .slice(0, 3);
  }

  _sideHtml(d) {
    const pots = this._allPots(d);
    const sug = this._suggestions(d);
    const cats = window._fd.CAT_LABELS || {};
    return `<section class="card"><div class="h"><span>${this._t("home.desk.manage")} <span class="dtag">${this._t("home.desk.marker")}</span></span></div>
      ${pots.length ? pots.map((p) => this._confirmId === p.id ? `<div class="mg" role="alertdialog" aria-label="${this._e(this._t("home.pot.delete_confirm", { name: p.name }))}"><span>${this._e(this._t("home.pot.delete_confirm", { name: p.name }))}</span>
        <span class="btns"><button class="btn ghost sm" data-act="delno">${this._t("home.pot.cancel")}</button>
        <button class="btn danger sm" data-act="delyes" data-id="${this._e(p.id)}">${this._t("home.pot.delete")}</button></span></div>` : `<div class="mg"><span><b>${this._e(p.name)}</b><small class="muted">${this._m(p.cycle_budget, false)} · ${p.owner === "shared" ? this._t("home.pot.owner.shared") : this._e(p.owner)}</small></span>
        <span class="btns"><button class="btn ghost sm" data-act="editpot" data-id="${this._e(p.id)}">${this._t("home.pot.edit_btn")}</button>
        <button class="btn danger sm" data-act="delpot" data-id="${this._e(p.id)}">${this._t("home.pot.delete")}</button></span></div>`).join("")
        : `<div class="muted">${this._t("home.pots.empty")}</div>`}
      <div class="acts"><button class="btn dsk" data-act="addpot">+ ${this._t("home.pot.new")}</button></div></section>
    <section class="card"><div class="h"><span>${this._t("home.desk.suggest")} <span class="dtag">${this._t("home.desk.marker")}</span></span></div>
      ${sug.length ? sug.map((k) => `<div class="sug"><div>${this._t("home.desk.suggest_text", { category: this._e(cats[k] || k) })}</div>
        <div class="acts" style="margin-top:6px"><button class="btn ghost sm" data-act="sugdismiss" data-k="${this._e(k)}">${this._t("home.desk.suggest_dismiss")}</button>
        <button class="btn sm dsk" data-act="sugcreate" data-k="${this._e(k)}">${this._t("home.desk.suggest_create")}</button></div></div>`).join("")
        : `<div class="muted">${this._t("home.desk.suggest_none")}</div>`}</section>`;
  }

  // ---- pot sheet --------------------------------------------------------
  _openSheet(pot, preset) {
    const d = this._data || {};
    const base = pot || { name: "", cycle_budget: "", kind: "spend", category_keys: [], owner: d.view === "household" || !d.person ? "shared" : d.person.name, ...(preset || {}) };
    this._sheet = { id: pot ? pot.id : null, name: base.name, budget: base.cycle_budget, kind: base.kind || "spend", owner: base.owner, cats: [...(base.category_keys || [])], error: "" };
    this._returnFocus = this.shadowRoot.activeElement;
    this._paintSheet();
  }

  _closeSheet() {
    this._sheet = null;
    this.shadowRoot.getElementById("sheet").innerHTML = "";
    if (this._returnFocus && this._returnFocus.focus) this._returnFocus.focus();
  }

  _paintSheet() {
    const s = this._sheet;
    const host = this.shadowRoot.getElementById("sheet");
    if (!s) { host.innerHTML = ""; return; }
    const d = this._data || {};
    const owners = [["shared", this._t("home.pot.owner.shared")]];
    if (d.person) owners.unshift([d.person.name, d.person.name]);
    const cats = Object.entries(window._fd.CAT_LABELS || {}).filter(([k]) => !SUGGEST_SKIP.has(k));
    host.innerHTML = `<div class="scrim" data-act="scrim"><form class="sheet" role="dialog" aria-modal="true" aria-label="${this._t(s.id ? "home.pot.edit" : "home.pot.new")}" data-form>
      <div class="h"><span>${this._t(s.id ? "home.pot.edit" : "home.pot.new")}</span></div>
      <label for="pn">${this._t("home.pot.name")}</label><input id="pn" type="text" maxlength="60" value="${this._e(s.name)}" autocomplete="off">
      <label for="pb">${this._t("home.pot.budget")}</label><input id="pb" type="number" inputmode="decimal" min="0" step="1" value="${this._e(String(s.budget))}">
      <div class="lbl">${this._t("home.pot.kind")}</div><div class="opts" role="radiogroup">${["spend", "reserve"].map((k) => `<button type="button" role="radio" data-kind="${k}" aria-checked="${s.kind === k}">${this._t("home.pot.kind." + k)}</button>`).join("")}</div>
      <div class="lbl">${this._t("home.pot.owner")}</div><div class="opts" role="radiogroup">${owners.map(([v, l]) => `<button type="button" role="radio" data-owner="${this._e(v)}" aria-checked="${s.owner === v}">${this._e(l)}</button>`).join("")}</div>
      <div class="lbl">${this._t("home.pot.categories")}</div><div class="opts">${cats.map(([k, l]) => `<button type="button" data-cat="${k}" aria-pressed="${s.cats.includes(k)}">${this._e(l)}</button>`).join("")}</div>
      <div class="err" id="sheeterr" role="alert">${this._e(s.error)}</div>
      <div class="acts"><button type="button" class="btn ghost" data-act="cancel">${this._t("home.pot.cancel")}</button><button type="submit" class="btn">${this._t("home.pot.save")}</button></div></form></div>`;
    const form = host.querySelector("[data-form]");
    form.addEventListener("submit", (e) => { e.preventDefault(); this._savePot(); });
    form.addEventListener("input", () => {
      s.name = host.querySelector("#pn").value;
      s.budget = host.querySelector("#pb").value;
    });
    const first = host.querySelector("#pn");
    if (first) first.focus();
  }

  async _savePot() {
    const s = this._sheet;
    const budget = parseFloat(String(s.budget).replace(",", "."));
    if (!s.name.trim() || !(budget >= 0) || String(s.budget) === "") {
      s.error = this._t("home.pot.invalid");
      this.shadowRoot.getElementById("sheeterr").textContent = s.error;
      return;
    }
    const body = { name: s.name.trim(), owner: s.owner, cycle_budget: budget, category_keys: s.cats, kind: s.kind };
    if (s.id) body.id = s.id;
    try {
      await this._hass.callApi(s.id ? "PUT" : "POST", `${DOMAIN}/pots`, body);
      this._closeSheet();
      this._toast(this._t("home.pot.saved"));
      this._load();
    } catch (e) {
      s.error = this._t("home.pot.failed");
      this.shadowRoot.getElementById("sheeterr").textContent = s.error;
    }
  }

  async _deletePot(id) {
    const p = this._allPots(this._data || {}).find((x) => x.id === id);
    this._confirmId = null;
    if (!p) return;
    try {
      await this._hass.callApi("DELETE", `${DOMAIN}/pots?id=${encodeURIComponent(id)}`);
      this._load();
    } catch (e) {
      this._toast(this._t("home.pot.failed"));
    }
  }

  // ---- events -----------------------------------------------------------
  _onClick(e) {
    const t = e.target.closest("[data-h],[data-v],[data-act],[data-kind],[data-owner],[data-cat]");
    if (!t) return;
    const s = this._sheet;
    if (t.dataset.kind && s) { s.kind = t.dataset.kind; this._paintSheet(); return; }
    if (t.dataset.owner !== undefined && s) { s.owner = t.dataset.owner; this._paintSheet(); return; }
    if (t.dataset.cat && s) {
      s.cats = s.cats.includes(t.dataset.cat) ? s.cats.filter((c) => c !== t.dataset.cat) : [...s.cats, t.dataset.cat];
      this._paintSheet();
      return;
    }
    if (t.dataset.h) { this._setHorizon(t.dataset.h); return; }
    if (t.dataset.v) { if (!t.disabled) this._setView(t.dataset.v); return; }
    const pot = (id) => this._allPots(this._data || {}).find((p) => p.id === id);
    switch (t.dataset.act) {
      case "alerts": this._alertsOpen = !this._alertsOpen; this._paint(); break;
      case "fresh": this._freshOpen = !this._freshOpen; this._paint(); break;
      case "refresh": this.dispatchEvent(new CustomEvent("fd-refresh-requested", { bubbles: true, composed: true })); break;
      case "renew": window._fd.navigate(window._fd.INTEGRATION_PATH, e); break;
      case "ask":
        this.dispatchEvent(new CustomEvent("fd-categorize-requested", { bubbles: true, composed: true }));
        break;
      case "retry": this._load(); break;
      case "demo": this.dispatchEvent(new CustomEvent("fd-demo-toggle", { bubbles: true, composed: true })); break;
      case "flip": this._flipped = !this._flipped; this._paint(); break;
      case "more": this._moreNext = !this._moreNext; this._paint(); break;
      case "addpot": this._openSheet(null); break;
      case "settings": this.dispatchEvent(new CustomEvent("fd-open-settings", { bubbles: true, composed: true })); break;
      case "editpot": this._openSheet(pot(t.dataset.id)); break;
      case "delpot": this._confirmId = t.dataset.id; this._paint(); break;
      case "delyes": this._deletePot(t.dataset.id); break;
      case "delno": this._confirmId = null; this._paint(); break;
      case "cancel": this._closeSheet(); break;
      case "scrim": if (e.target === t) this._closeSheet(); break;
      case "sugcreate": {
        const k = t.dataset.k;
        this._openSheet(null, { name: (window._fd.CAT_LABELS || {})[k] || k, category_keys: [k] });
        break;
      }
      case "sugdismiss": {
        let list = [];
        try { list = JSON.parse(localStorage.getItem(DISMISS_KEY) || "[]"); } catch (_) { /* ignore */ }
        list.push(t.dataset.k);
        try { localStorage.setItem(DISMISS_KEY, JSON.stringify(list)); } catch (_) { /* ignore */ }
        this._paint();
        break;
      }
      default: break;
    }
  }
}

window._fd.defineOnce("fd-home", FdHome);
