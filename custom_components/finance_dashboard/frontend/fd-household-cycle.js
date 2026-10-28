/**
 * fd-household-cycle — the Household tab's honest KPI block (replaces the
 * calendar-month stats row).
 *
 *   GET finance_dashboard/household_summary?cycle=current|previous
 *   (contract: docs/dev/contracts/household-summary.md; cache read, never a bank call)
 *
 * Shows the cycle (label, dates, day x/y), Einnahmen · Ausgaben · Überschuss with
 * the previous-cycle delta, Sparquote (or why there is none), Fix vs Variabel and
 * the owner split (restricted persons: totals only). Every block carries one plain
 * rule-based sentence and, where something is open, one action.
 *
 * Properties: hass (required), data (any set re-reads the summary).
 * Events (bubbling, composed):
 *   fd-navigate          {target:"setup"} — not configured: setup wizard
 *   fd-open-settings     —                — accounts without owner
 *   fd-refresh-requested —                — empty cycle: import
 */

const DOMAIN = "finance_dashboard";

/*FB-START*/
const FB = {
  de: {
    "hc.cycle": "Zyklus",
    "hc.cycle.day": "Tag $day von $days",
    "hc.cycle.current": "Dieser Zyklus",
    "hc.cycle.previous": "Letzter Zyklus",
    "hc.cycle.calendar": "Kalendermonat, bis ein Gehaltseingang erkannt ist.",
    "hc.cycle.household": "Der Zyklus beginnt mit dem Gehaltseingang im Haushalt.",
    "hc.income": "Einnahmen",
    "hc.expenses": "Ausgaben",
    "hc.surplus": "Überschuss",
    "hc.savings": "Sparquote",
    "hc.vs_prev": "$delta zum Vorzyklus",
    "hc.no_prev": "kein Vergleichszyklus",
    "hc.same": "unverändert zum Vorzyklus",
    "hc.savings.pending": "Gehalt erwartet am $date",
    "hc.savings.pending_nodate": "Gehalt noch erwartet",
    "hc.savings.none": "noch kein Einkommen im Zyklus",
    "hc.say.income": "In diesem Zyklus sind $amount eingegangen.",
    "hc.say.income_pending": "Bisher sind $amount eingegangen – das Gehalt fehlt noch, die Zahlen sind noch unvollständig.",
    "hc.say.income_none": "In diesem Zyklus ist noch kein Einkommen erkannt worden.",
    "hc.say.expenses": "Ausgegeben wurden $amount.",
    "hc.say.surplus_pos": "Bisher bleiben $amount übrig.",
    "hc.say.surplus_neg": "Bisher wurden $amount mehr ausgegeben als eingenommen.",
    "hc.say.surplus_neg_pending": "Bisher $amount mehr Ausgaben als Einnahmen – mit dem erwarteten Gehalt ändert sich das.",
    "hc.say.savings": "Von jedem eingenommenen Euro bleiben $pct Cent übrig.",
    "hc.say.savings_neg": "Bisher geht mehr raus als rein.",
    "hc.fixvar": "Fix und variabel",
    "hc.fixed": "Fix",
    "hc.variable": "Variabel",
    "hc.say.fixvar": "Davon sind $fixed fix (Verträge, Abos, Plan-Fixkosten) und $variable variabel.",
    "hc.say.fixvar_none": "Noch keine Ausgaben in diesem Zyklus.",
    "hc.owners": "Fixkosten und Ausgaben nach Person",
    "hc.owner.shared": "Haushalt",
    "hc.owner.open": "Nicht zugeordnet",
    "hc.owner.restricted": "nur Summe sichtbar",
    "hc.owner.spent": "Ausgaben $amount",
    "hc.owner.fix": "fix $amount",
    "hc.owner.var": "variabel $amount",
    "hc.owner.surplus": "Überschuss $amount",
    "hc.say.owners": "Der Haushalt trägt $shared der Ausgaben, auf Personen entfallen $persons.",
    "hc.say.open": "$amount Ausgaben gehören noch keinem Konto-Besitzer.",
    "hc.open.action": "Konten zuordnen",
    "hc.empty.title": "In diesem Zyklus sind noch keine Buchungen.",
    "hc.empty.body": "Hol die aktuellen Umsätze von der Bank, dann füllt sich diese Ansicht.",
    "hc.empty.action": "Neu importieren",
    "hc.nc.title": "Der Haushalt ist noch nicht eingerichtet.",
    "hc.nc.body": "Mit dem Einrichtungsassistenten verbindest du Bank, Personen und Plan in wenigen Schritten.",
    "hc.nc.action": "Einrichtung starten",
    "hc.error": "Die Zyklusübersicht konnte nicht geladen werden.",
    "hc.retry": "Erneut versuchen",
    "hc.loading": "Wird geladen …",
    "hc.plan.cta": "Plan einrichten",
    "hc.plan.empty": "Noch kein Plan vorhanden. Der Einrichtungsassistent legt Einkommen und Kostenpositionen mit Zuordnung an – oder übernimmt sie aus deiner Tabelle.",
  },
  en: {
    "hc.cycle": "Cycle",
    "hc.cycle.day": "Day $day of $days",
    "hc.cycle.current": "This cycle",
    "hc.cycle.previous": "Last cycle",
    "hc.cycle.calendar": "Calendar month until a salary deposit is detected.",
    "hc.cycle.household": "The cycle starts with the household's salary deposit.",
    "hc.income": "Income",
    "hc.expenses": "Expenses",
    "hc.surplus": "Surplus",
    "hc.savings": "Savings rate",
    "hc.vs_prev": "$delta vs. previous cycle",
    "hc.no_prev": "no comparison cycle",
    "hc.same": "unchanged vs. previous cycle",
    "hc.savings.pending": "Salary expected on $date",
    "hc.savings.pending_nodate": "Salary still expected",
    "hc.savings.none": "no income in this cycle yet",
    "hc.say.income": "$amount came in during this cycle.",
    "hc.say.income_pending": "$amount came in so far – the salary is still missing, so the figures are incomplete.",
    "hc.say.income_none": "No income has been detected in this cycle yet.",
    "hc.say.expenses": "$amount was spent.",
    "hc.say.surplus_pos": "$amount is left so far.",
    "hc.say.surplus_neg": "So far $amount more went out than came in.",
    "hc.say.surplus_neg_pending": "So far $amount more went out than came in – the expected salary will change that.",
    "hc.say.savings": "Of every euro that came in, $pct cents are left.",
    "hc.say.savings_neg": "So far more goes out than comes in.",
    "hc.fixvar": "Fixed and variable",
    "hc.fixed": "Fixed",
    "hc.variable": "Variable",
    "hc.say.fixvar": "Of that, $fixed is fixed (contracts, subscriptions, plan fixed costs) and $variable is variable.",
    "hc.say.fixvar_none": "No expenses in this cycle yet.",
    "hc.owners": "Fixed costs and expenses by person",
    "hc.owner.shared": "Household",
    "hc.owner.open": "Not assigned",
    "hc.owner.restricted": "totals only",
    "hc.owner.spent": "Expenses $amount",
    "hc.owner.fix": "fixed $amount",
    "hc.owner.var": "variable $amount",
    "hc.owner.surplus": "Surplus $amount",
    "hc.say.owners": "The household carries $shared of the expenses, persons account for $persons.",
    "hc.say.open": "$amount of expenses do not belong to an account owner yet.",
    "hc.open.action": "Assign accounts",
    "hc.empty.title": "There are no bookings in this cycle yet.",
    "hc.empty.body": "Fetch the latest transactions from the bank and this view fills up.",
    "hc.empty.action": "Import again",
    "hc.nc.title": "The household is not set up yet.",
    "hc.nc.body": "The setup wizard connects bank, people and plan in a few steps.",
    "hc.nc.action": "Start setup",
    "hc.error": "The cycle overview could not be loaded.",
    "hc.retry": "Try again",
    "hc.loading": "Loading …",
    "hc.plan.cta": "Set up the plan",
    "hc.plan.empty": "No plan yet. The setup wizard creates income and cost positions with owners – or takes them over from your spreadsheet.",
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

const PERSON_COLORS = ["var(--fd-person-a)", "var(--fd-person-b)", "#ef6c00", "#5e35b1", "#6d4c41"];

const CSS = `
:host { display: block; margin-bottom: 14px; }
.root { color: var(--fd-t1); font-size: 13px; line-height: 1.4; }
button { font: inherit; color: inherit; cursor: pointer; }
.card { padding: 14px 16px; border-radius: var(--fd-r-card); background: var(--fd-card); box-shadow: var(--fd-sh1); margin-bottom: 12px; }
.head { display: flex; align-items: center; justify-content: space-between; gap: 8px 12px; flex-wrap: wrap; }
.head h3 { margin: 0; font-size: 16px; font-weight: 500; }
.head .sub { color: var(--fd-t2); font-size: 12px; }
.prog { height: 6px; margin: 10px 0 0; border-radius: 3px; background: var(--fd-sunk); overflow: hidden; }
.prog i { display: block; height: 100%; background: var(--fd-a500); }
.seg { display: inline-flex; border: 1px solid var(--fd-line); border-radius: var(--fd-r-pill); overflow: hidden; }
.seg button { min-height: var(--fd-touch); padding: 0 14px; border: 0; background: transparent; }
.seg button[aria-checked="true"] { background: var(--fd-a50); color: var(--fd-a900); font-weight: 500; }
.kpis { display: grid; grid-template-columns: 1fr; gap: 12px; margin-bottom: 12px; }
@media (min-width: 640px) { .kpis { grid-template-columns: repeat(3, 1fr); } }
.kpi { padding: 14px 16px; border-radius: var(--fd-r-card); background: var(--fd-card); box-shadow: var(--fd-sh1); }
.lab { color: var(--fd-t2); font-size: 12px; }
.kpi .val { margin: 2px 0; font-size: 26px; font-weight: 500; line-height: 1.1; font-variant-numeric: tabular-nums; }
.kpi .val.ok { color: var(--fd-ok); }
.kpi .delta { color: var(--fd-t2); font-size: 11.5px; }
.say { margin: 8px 0 0; color: var(--fd-t2); font-size: 12.5px; }
.sav { display: flex; align-items: baseline; gap: 4px 12px; flex-wrap: wrap; }
.sav b { font-size: 18px; font-weight: 500; }
.sav span { color: var(--fd-t2); }
h4 { margin: 0 0 8px; font-size: 14px; font-weight: 500; }
.bar { display: flex; height: 12px; border-radius: 6px; overflow: hidden; background: var(--fd-sunk); }
.bar div { height: 100%; }
.leg { display: flex; flex-wrap: wrap; gap: 4px 16px; margin-top: 8px; }
.leg span { display: inline-flex; align-items: center; gap: 6px; }
.leg i { width: 8px; height: 8px; border-radius: 50%; }
.leg b { font-weight: 500; font-variant-numeric: tabular-nums; }
.own { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 12px; padding: 10px 0 10px 12px; border-left: 4px solid var(--c); margin-top: 8px; }
.own .nm { flex: 1 1 140px; font-weight: 500; }
.own .big { font-variant-numeric: tabular-nums; font-weight: 500; }
.own .sm { flex: 1 1 100%; color: var(--fd-t2); font-size: 11.5px; display: flex; flex-wrap: wrap; gap: 2px 12px; }
.own .rn { flex: 1 1 100%; color: var(--fd-t2); font-size: 11.5px; }
.act { display: flex; align-items: center; justify-content: space-between; gap: 8px 12px; flex-wrap: wrap; margin-top: 10px; padding: 8px 12px; border-radius: 10px; background: var(--fd-near-bg); }
.btn { min-height: var(--fd-touch); padding: 0 16px; border: 1px solid transparent; border-radius: var(--fd-r-pill); background: var(--fd-a700); color: #fff; font-weight: 500; }
.btn.ghost { background: transparent; color: var(--fd-a700); border-color: var(--fd-a100); }
.empty { padding: 4px 0; color: var(--fd-t2); line-height: 1.6; }
.empty b { display: block; color: var(--fd-t1); font-weight: 500; }
.empty .btn { margin-top: 10px; }
.note { color: var(--fd-t2); font-size: 11.5px; margin-top: 6px; }
`;

class FdHouseholdCycle extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._cycle = "current";
    this._sum = null;
    this._state = "loading"; // loading | ok | nc | error
    this._seq = 0;
    this._built = false;
  }

  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    if (first) this.reload();
  }

  /** The panel pushes new data on every refresh; re-read the summary then. */
  set data(_v) {
    if (this._hass && this._built) this.reload();
  }

  async reload() {
    if (!this._hass) return;
    const seq = ++this._seq;
    await window._fd.t("hc.cycle");
    if (!this._built) { this._built = true; this._bind(); }
    if (!this._sum) { this._state = "loading"; this._render(); }
    try {
      const r = await this._hass.callApi("GET", `${DOMAIN}/household_summary?cycle=${this._cycle}`);
      if (seq !== this._seq) return;
      this._sum = r;
      this._state = "ok";
    } catch (e) {
      if (seq !== this._seq) return;
      this._state = e && e.status_code === 404 ? "nc" : "error";
    }
    this._render();
  }

  _bind() {
    this.shadowRoot.addEventListener("click", (ev) => {
      const t = ev.target.closest("[data-act],[data-cycle]");
      if (!t) return;
      if (t.dataset.cycle) { this._cycle = t.dataset.cycle; this.reload(); return; }
      const fire = (name, detail) => this.dispatchEvent(new CustomEvent(name, { bubbles: true, composed: true, detail }));
      switch (t.dataset.act) {
        case "setup": fire("fd-navigate", { target: "setup" }); break;
        case "assign": fire("fd-open-settings"); break;
        case "import": fire("fd-refresh-requested"); break;
        case "retry": this.reload(); break;
        default: break;
      }
    });
  }

  _delta(line) {
    // Neutral wording, never a red alarm: a delta is information, not a verdict.
    if (!line || line.delta == null) return tr("hc.no_prev");
    if (Math.abs(line.delta) < 0.005) return tr("hc.same");
    return tr("hc.vs_prev", { delta: `${line.delta > 0 ? "+" : "−"}${window._fd.eur(Math.abs(line.delta))}` });
  }

  _render() {
    if (!this._built) return;
    const { SHARED_CSS } = window._fd;
    let body;
    if (this._state === "loading") body = `<div class="card"><div class="empty">${tr("hc.loading")}</div></div>`;
    else if (this._state === "nc") {
      body = `<div class="card"><div class="empty"><b>${tr("hc.nc.title")}</b>${tr("hc.nc.body")}<br>
        <button class="btn" data-act="setup">${tr("hc.nc.action")}</button></div></div>`;
    } else if (this._state === "error") {
      body = `<div class="card"><div class="empty"><b>${tr("hc.error")}</b>
        <button class="btn ghost" data-act="retry">${tr("hc.retry")}</button></div></div>`;
    } else body = this._body(this._sum || {});
    this.shadowRoot.innerHTML = `<style>${SHARED_CSS}${CSS}</style><div class="root">${body}</div>`;
  }

  _body(s) {
    const { eur, escHtml } = window._fd;
    const c = s.cycle || {};
    const L = s.lines || {};
    const income = s.income || 0, expenses = s.expenses || 0, surplus = s.surplus || 0;
    const fixed = s.fixed || 0, variable = s.variable || 0;
    const lang = (window._fd._hass && window._fd._hass.language) || navigator.language || "de";
    const fmtD = (iso) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString(lang, { day: "numeric", month: "numeric" }) : "");
    const range = c.start && c.end ? `${fmtD(c.start)} – ${fmtD(c.end)}` : "";
    const isCur = (c.selected || this._cycle) === "current";
    const pct = c.days > 0 && c.day > 0 ? Math.min(100, Math.round(c.day / c.days * 100)) : 0;
    const ruleNote = c.rule === "calendar_fallback" ? tr("hc.cycle.calendar") : tr("hc.cycle.household");

    const head = `<div class="card">
  <div class="head">
    <div><h3>${tr("hc.cycle")} ${escHtml(range)}</h3>
      <div class="sub">${isCur && c.day ? escHtml(tr("hc.cycle.day", { day: c.day, days: c.days })) : ""}</div></div>
    <div class="seg" role="radiogroup" aria-label="${tr("hc.cycle")}">
      <button role="radio" data-cycle="current" aria-checked="${this._cycle === "current"}">${tr("hc.cycle.current")}</button>
      <button role="radio" data-cycle="previous" aria-checked="${this._cycle === "previous"}">${tr("hc.cycle.previous")}</button>
    </div>
  </div>
  ${isCur && pct ? `<div class="prog" role="img" aria-label="${pct} %"><i style="width:${pct}%"></i></div>` : ""}
  <div class="note">${escHtml(ruleNote)}</div>
</div>`;

    const pending = !!s.income_pending;
    // Empty cycle: say what to do instead of three zero-valued cards.
    if (income === 0 && expenses === 0 && !pending) {
      return `${head}<div class="card"><div class="empty"><b>${tr("hc.empty.title")}</b>${tr("hc.empty.body")}<br>
        <button class="btn" data-act="import">${tr("hc.empty.action")}</button></div></div>`;
    }

    const sayIncome = pending ? tr("hc.say.income_pending", { amount: eur(income) })
      : income > 0 ? tr("hc.say.income", { amount: eur(income) }) : tr("hc.say.income_none");
    const saySurplus = surplus >= 0 ? tr("hc.say.surplus_pos", { amount: eur(surplus) })
      : tr(pending ? "hc.say.surplus_neg_pending" : "hc.say.surplus_neg", { amount: eur(Math.abs(surplus)) });

    const kpis = `<div class="kpis">
  <div class="kpi"><div class="lab">${tr("hc.income")}</div><div class="val">${eur(income)}</div>
    <div class="delta">${escHtml(this._delta(L.income))}</div><p class="say">${escHtml(sayIncome)}</p></div>
  <div class="kpi"><div class="lab">${tr("hc.expenses")}</div><div class="val">${eur(expenses)}</div>
    <div class="delta">${escHtml(this._delta(L.expenses))}</div><p class="say">${escHtml(tr("hc.say.expenses", { amount: eur(expenses) }))}</p></div>
  <div class="kpi"><div class="lab">${tr("hc.surplus")}</div><div class="val ${surplus >= 0 ? "ok" : ""}">${surplus < 0 ? "−" : ""}${eur(Math.abs(surplus))}</div>
    <div class="delta">${escHtml(this._delta(L.surplus))}</div><p class="say">${escHtml(saySurplus)}</p></div>
</div>`;

    // Sparquote: never a number without income (no "-786 %").
    let sav;
    if (s.savings_rate != null) {
      const p = Math.round(s.savings_rate * (Math.abs(s.savings_rate) <= 1.5 ? 100 : 1));
      sav = `<b>${p} %</b><span>${escHtml(s.savings_rate < 0 ? tr("hc.say.savings_neg") : tr("hc.say.savings", { pct: Math.max(0, p) }))}</span>`;
    } else if (pending) {
      sav = `<b>–</b><span>${escHtml(s.expected_income_date ? tr("hc.savings.pending", { date: fmtD(s.expected_income_date) }) : tr("hc.savings.pending_nodate"))}</span>`;
    } else sav = `<b>–</b><span>${escHtml(tr("hc.savings.none"))}</span>`;
    const savings = `<div class="card"><div class="lab">${tr("hc.savings")}</div><div class="sav">${sav}</div></div>`;

    // Fix vs Variabel
    const tot = fixed + variable;
    const fp = tot > 0 ? fixed / tot * 100 : 0;
    const fixvar = `<div class="card"><h4>${tr("hc.fixvar")}</h4>
  ${tot > 0 ? `<div class="bar" role="img" aria-label="${tr("hc.fixvar")}"><div style="width:${fp}%;background:var(--fd-a700)"></div><div style="width:${100 - fp}%;background:var(--fd-a300)"></div></div>
  <div class="leg"><span><i style="background:var(--fd-a700)"></i>${tr("hc.fixed")} <b>${eur(fixed)}</b></span><span><i style="background:var(--fd-a300)"></i>${tr("hc.variable")} <b>${eur(variable)}</b></span></div>
  <p class="say">${escHtml(tr("hc.say.fixvar", { fixed: eur(fixed), variable: eur(variable) }))}</p>`
    : `<p class="say" style="margin:0">${tr("hc.say.fixvar_none")}</p>`}</div>`;

    // Owners: restricted persons show their expense total only.
    const owners = s.owners || [];
    let pi = 0;
    const rows = owners.map((o) => {
      const kind = o.kind || "person";
      const color = kind === "shared" ? "var(--fd-household)" : kind === "open" ? "var(--fd-t3)" : PERSON_COLORS[pi++ % PERSON_COLORS.length];
      const name = kind === "shared" ? tr("hc.owner.shared") : kind === "open" ? tr("hc.owner.open") : o.owner;
      const small = o.restricted ? `<div class="rn">${escHtml(tr("hc.owner.restricted"))}</div>` : `<div class="sm">
        ${o.fixed != null ? `<span>${escHtml(tr("hc.owner.fix", { amount: eur(o.fixed) }))}</span>` : ""}
        ${o.variable != null ? `<span>${escHtml(tr("hc.owner.var", { amount: eur(o.variable) }))}</span>` : ""}
        ${kind === "person" ? `<span>${escHtml(tr("hc.owner.surplus", { amount: eur(o.surplus || 0) }))}</span>` : ""}</div>`;
      return `<div class="own" style="--c:${color}"><span class="nm">${escHtml(name)}</span><span class="big">${escHtml(tr("hc.owner.spent", { amount: eur(o.expenses || 0) }))}</span>${small}</div>`;
    });
    const sum = (k) => owners.filter((o) => o.kind === k).reduce((a, o) => a + (o.expenses || 0), 0);
    const openExp = sum("open");
    const ownCard = rows.length ? `<div class="card"><h4>${tr("hc.owners")}</h4>${rows.join("")}
  ${expenses > 0 ? `<p class="say">${escHtml(tr("hc.say.owners", { shared: eur(sum("shared")), persons: eur(sum("person")) }))}</p>` : ""}
  ${openExp > 0 ? `<div class="act"><span>${escHtml(tr("hc.say.open", { amount: eur(openExp) }))}</span><button class="btn ghost" data-act="assign">${tr("hc.open.action")}</button></div>` : ""}</div>` : "";

    return `${head}${kpis}${savings}${fixvar}${ownCard}`;
  }
}

window._fd.defineOnce("fd-household-cycle", FdHouseholdCycle);
