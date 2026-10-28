/**
 * fd-setup — guided setup wizard (admin only), full-screen step flow.
 *
 *   GET/PUT finance_dashboard/setup                {current_step, steps{}, completed, ai_opt_in, notifications{}, persons[{name,payday}]}
 *   GET     finance_dashboard/setup/payday_suggestions   {suggestions:[{person, confirmed_day, suggested_day, source, amount}]}
 *   GET/POST finance_dashboard/setup/pot_suggestions     {suggestions:[{owner, category, name, cycle_budget, samples}]}
 *
 * Steps: persons, accounts (both embed <fd-settings section="...">), payday, pots, plan,
 * notifications, ai, done. Every "Weiter" stores the step on the server, so the wizard
 * resumes at the first unresolved step. Nothing here talks to the bank.
 *
 * Properties: hass (required).
 * Events (bubbling, composed):
 *   fd-setup-close   {completed}  — panel removes the overlay and reloads Start
 *   fd-toast         {message, type}
 */

const DOMAIN = "finance_dashboard";
const STEPS = ["persons", "accounts", "payday", "region", "pots", "plan", "notifications", "ai", "done"];
const SKIPPABLE = new Set(["payday", "region", "pots", "plan", "notifications", "ai"]);

// Fallback texts: used until locales/*.json carry the setup.* keys.
// Federal states (ISO 3166-2:DE) for the benchmark comparison.
const STATES = [
  ["DE-BW", "Baden-Württemberg"], ["DE-BY", "Bayern"], ["DE-BE", "Berlin"], ["DE-BB", "Brandenburg"],
  ["DE-HB", "Bremen"], ["DE-HH", "Hamburg"], ["DE-HE", "Hessen"], ["DE-MV", "Mecklenburg-Vorpommern"],
  ["DE-NI", "Niedersachsen"], ["DE-NW", "Nordrhein-Westfalen"], ["DE-RP", "Rheinland-Pfalz"], ["DE-SL", "Saarland"],
  ["DE-SN", "Sachsen"], ["DE-ST", "Sachsen-Anhalt"], ["DE-SH", "Schleswig-Holstein"], ["DE-TH", "Thüringen"],
];

const FB = {
  de: {
    "setup.title": "Einrichtung",
    "setup.step_of": "Schritt $n von $total",
    "setup.later": "Später",
    "setup.back": "Zurück",
    "setup.next": "Weiter",
    "setup.skip": "Überspringen",
    "setup.saving": "Speichere…",
    "setup.error": "Speichern fehlgeschlagen",
    "setup.load_error": "Die Einrichtung konnte nicht geladen werden.",
    "setup.retry": "Erneut versuchen",
    "setup.admin_only": "Die Einrichtung übernimmt ein Administrator. Du musst nichts tun.",
    "setup.persons.title": "Wer gehört zum Haushalt?",
    "setup.persons.body": "Jeder Home-Assistant-Benutzer, der mitmacht, wird eine Person. Namen kannst du anpassen.",
    "setup.persons.need_one": "Wähle mindestens eine Person.",
    "setup.accounts.title": "Welches Konto gehört wem?",
    "setup.accounts.body": "Das ist nur der Standard. Budgetposten und Korrekturen gehen vor. Offene Konten kannst du später zuordnen.",
    "setup.payday.title": "Wann ist Zahltag?",
    "setup.payday.body": "Dein Monat beginnt mit dem Gehalt. Wir haben auf deinen Konten nach dem größten regelmäßigen Eingang gesucht.",
    "setup.payday.day": "Tag im Monat",
    "setup.payday.suggest": "Vorschlag: der $day. (aus $source, ca. $amount)",
    "setup.payday.suggest_short": "Vorschlag: der $day.",
    "setup.payday.none": "Kein Vorschlag gefunden. Trag den Tag ein oder lass das Feld leer, dann gilt der Kalendermonat.",
    "setup.payday.use": "Übernehmen",
    "setup.payday.confirmed": "Bestätigt",
    "setup.payday.no_persons": "Noch keine Personen. Dieser Schritt kann warten.",
    "setup.payday.err": "Der Tag muss zwischen 1 und 31 liegen.",
    "setup.region.title": "Wo wohnt ihr?",
    "setup.region.body": "Das Bundesland brauchen wir nur für den Vergleich mit typischen Ausgaben in deiner Region. Die Postleitzahl ist freiwillig.",
    "setup.region.state": "Bundesland",
    "setup.region.postcode": "Postleitzahl (optional)",
    "setup.region.err_postcode": "Die Postleitzahl hat 5 Ziffern.",
    "setup.summary.region": "Region",
    "setup.pots.title": "Töpfe aus deiner Historie",
    "setup.pots.body": "So viel hast du in den letzten Monaten typischerweise ausgegeben. Wähle, was zu Töpfen werden soll, und passe die Beträge an.",
    "setup.pots.samples": "aus $n Monaten",
    "setup.pots.per_cycle": "pro Monat",
    "setup.pots.amount": "Betrag",
    "setup.pots.empty": "Noch nicht genug Historie für Vorschläge. Töpfe legst du später auf Start an, sobald ein paar Monate Daten da sind.",
    "setup.pots.created": "$n Töpfe angelegt",
    "setup.pots.owner_shared": "Haushalt",
    "setup.plan.title": "Budgetplan",
    "setup.plan.body": "Der Plan hält fest, was ihr fest eingeplant habt: Fixkosten und Einkommen pro Person. Er ist ein Extra und für den Start nicht nötig.",
    "setup.plan.import": "Wenn du eine Haushaltstabelle (.xlsx) hast, kannst du sie importieren. Das geht über den Dienst finance_dashboard.import_spreadsheet in Home Assistant. Die Datei muss im Konfigurationsordner liegen.",
    "setup.plan.later": "Du kannst das jederzeit nachholen. Ohne Plan funktionieren Töpfe und Zyklus trotzdem.",
    "setup.notif.title": "Benachrichtigungen",
    "setup.notif.body": "Ruhig und selten: nur Ausnahmen und eine Wochenübersicht. Alles lässt sich abschalten.",
    "setup.notif.enabled": "Benachrichtigungen",
    "setup.notif.large_debit": "Ungewöhnlich hohe Abbuchung",
    "setup.notif.double_charge": "Doppelt abgebucht",
    "setup.notif.missing_salary": "Gehalt nicht eingegangen",
    "setup.notif.consent_expiring": "Bankzugang läuft bald ab",
    "setup.notif.digest_enabled": "Wochenübersicht",
    "setup.notif.factor": "Hoch heißt: mehr als das Faktor-fache des Üblichen",
    "setup.notif.factor_label": "Faktor",
    "setup.notif.threshold": "Oder ab diesem Betrag in Euro (0 = aus)",
    "setup.ai.title": "KI-Kategorisierung",
    "setup.ai.body": "Für Buchungen, die keine Regel erkennt, kann eine KI die Kategorie vorschlagen. Dafür wird zuerst die KI deiner Home-Assistant-Installation genutzt.",
    "setup.ai.privacy": "Gesendet werden nur Händlername und Verwendungszweck, nie Betrag, IBAN oder Datum. Ohne Zustimmung bleibt alles lokal.",
    "setup.ai.toggle": "KI-Kategorisierung erlauben",
    "setup.done.title": "Fertig",
    "setup.done.body": "Das ist dein Stand. Alles Übersprungene findest du später unter Einrichtung.",
    "setup.done.cta": "Zur Startseite",
    "setup.status.done": "erledigt",
    "setup.status.skipped": "übersprungen",
    "setup.status.pending": "offen",
    "setup.status.on": "an",
    "setup.status.off": "aus",
    "setup.summary.persons": "Personen",
    "setup.summary.accounts": "Konten",
    "setup.summary.payday": "Zahltag",
    "setup.summary.pots": "Töpfe",
    "setup.summary.plan": "Budgetplan",
    "setup.summary.notifications": "Benachrichtigungen",
    "setup.summary.ai": "KI-Kategorisierung",
  },
  en: {
    "setup.title": "Setup",
    "setup.step_of": "Step $n of $total",
    "setup.later": "Later",
    "setup.back": "Back",
    "setup.next": "Next",
    "setup.skip": "Skip",
    "setup.saving": "Saving…",
    "setup.error": "Saving failed",
    "setup.load_error": "The setup could not be loaded.",
    "setup.retry": "Try again",
    "setup.admin_only": "An administrator takes care of the setup. You do not need to do anything.",
    "setup.persons.title": "Who is part of the household?",
    "setup.persons.body": "Every Home Assistant user who takes part becomes a person. You can adjust the names.",
    "setup.persons.need_one": "Pick at least one person.",
    "setup.accounts.title": "Which account belongs to whom?",
    "setup.accounts.body": "This is only the default. Budget positions and corrections take precedence. You can assign open accounts later.",
    "setup.payday.title": "When is payday?",
    "setup.payday.body": "Your month starts with your salary. We looked for the largest regular deposit on your accounts.",
    "setup.payday.day": "Day of month",
    "setup.payday.suggest": "Suggestion: the $day. (from $source, about $amount)",
    "setup.payday.suggest_short": "Suggestion: the $day.",
    "setup.payday.none": "No suggestion found. Enter the day or leave it empty to use the calendar month.",
    "setup.payday.use": "Use",
    "setup.payday.confirmed": "Confirmed",
    "setup.payday.no_persons": "No people yet. This step can wait.",
    "setup.payday.err": "The day must be between 1 and 31.",
    "setup.region.title": "Where do you live?",
    "setup.region.body": "We only need the state to compare against typical spending in your region. The postcode is optional.",
    "setup.region.state": "State",
    "setup.region.postcode": "Postcode (optional)",
    "setup.region.err_postcode": "The postcode has 5 digits.",
    "setup.summary.region": "Region",
    "setup.pots.title": "Pots from your history",
    "setup.pots.body": "This is what you typically spent in recent months. Choose what becomes a pot and adjust the amounts.",
    "setup.pots.samples": "from $n months",
    "setup.pots.per_cycle": "per month",
    "setup.pots.amount": "Amount",
    "setup.pots.empty": "Not enough history for suggestions yet. You can add pots later on Start once a few months of data are in.",
    "setup.pots.created": "$n pots created",
    "setup.pots.owner_shared": "Household",
    "setup.plan.title": "Budget plan",
    "setup.plan.body": "The plan records what you set aside: fixed costs and income per person. It is an extra and not needed to start.",
    "setup.plan.import": "If you have a household spreadsheet (.xlsx) you can import it. This works through the finance_dashboard.import_spreadsheet service in Home Assistant. The file has to be in the config folder.",
    "setup.plan.later": "You can do this any time. Pots and cycle work without a plan.",
    "setup.notif.title": "Notifications",
    "setup.notif.body": "Quiet and rare: only exceptions and a weekly overview. Everything can be turned off.",
    "setup.notif.enabled": "Notifications",
    "setup.notif.large_debit": "Unusually large debit",
    "setup.notif.double_charge": "Charged twice",
    "setup.notif.missing_salary": "Salary not received",
    "setup.notif.consent_expiring": "Bank access expires soon",
    "setup.notif.digest_enabled": "Weekly overview",
    "setup.notif.factor": "Large means more than this factor times the usual",
    "setup.notif.factor_label": "Factor",
    "setup.notif.threshold": "Or from this amount in euros (0 = off)",
    "setup.ai.title": "AI categorisation",
    "setup.ai.body": "For transactions no rule recognises, an AI can suggest the category. Your Home Assistant's own AI is used first.",
    "setup.ai.privacy": "Only merchant name and remittance text are sent, never amount, IBAN or date. Without consent everything stays local.",
    "setup.ai.toggle": "Allow AI categorisation",
    "setup.done.title": "All set",
    "setup.done.body": "This is where you stand. Anything skipped can be done later under Setup.",
    "setup.done.cta": "Go to Start",
    "setup.status.done": "done",
    "setup.status.skipped": "skipped",
    "setup.status.pending": "open",
    "setup.status.on": "on",
    "setup.status.off": "off",
    "setup.summary.persons": "People",
    "setup.summary.accounts": "Accounts",
    "setup.summary.payday": "Payday",
    "setup.summary.pots": "Pots",
    "setup.summary.plan": "Budget plan",
    "setup.summary.notifications": "Notifications",
    "setup.summary.ai": "AI categorisation",
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
:host { display: block; position: fixed; inset: 0; z-index: 60; background: var(--fd-page); overflow-y: auto; overscroll-behavior: contain; }
.root { box-sizing: border-box; min-height: 100%; display: flex; flex-direction: column; color: var(--fd-t1); font-size: 14px; line-height: 1.45; container: wiz / inline-size; }
button { font: inherit; color: inherit; cursor: pointer; }
.top { display: flex; align-items: center; gap: 10px; padding: 10px 14px; max-width: 680px; width: 100%; box-sizing: border-box; margin: 0 auto; }
.top .lbl { flex: 1; color: var(--fd-t2); font-size: 12px; }
.dots { display: flex; gap: 6px; padding: 0 14px 4px; max-width: 680px; width: 100%; box-sizing: border-box; margin: 0 auto; list-style: none; }
.dots li { flex: 1; height: 5px; border-radius: 3px; background: var(--fd-line); }
.dots li.on { background: var(--fd-a300); }
.dots li.cur { background: var(--fd-a700); }
main { flex: 1; width: 100%; max-width: 680px; box-sizing: border-box; margin: 0 auto; padding: 8px 14px 96px; }
.card { padding: 16px; border-radius: var(--fd-r-card); background: var(--fd-card); box-shadow: var(--fd-sh1); }
h2 { margin: 0 0 4px; font-size: 19px; font-weight: 500; outline: none; }
.muted { color: var(--fd-t2); font-size: 12.5px; margin: 0 0 10px; }
.foot { position: sticky; bottom: 0; background: color-mix(in srgb, var(--fd-page) 92%, transparent); border-top: 1px solid var(--fd-line); padding: 10px 14px calc(10px + env(safe-area-inset-bottom, 0px)); backdrop-filter: blur(6px); }
.foot > div { max-width: 680px; margin: 0 auto; display: flex; align-items: center; gap: 8px; }
.foot .sp { flex: 1; }
.err { color: var(--fd-over); font-size: 12.5px; margin: 8px 0 0; min-height: 0; }
.btn { min-height: var(--fd-touch); padding: 0 18px; border: 1px solid transparent; border-radius: var(--fd-r-pill); background: var(--fd-a700); color: #fff; font-weight: 500; }
.btn.ghost { background: transparent; color: var(--fd-a700); border-color: var(--fd-a100); }
.btn.text { background: transparent; color: var(--fd-t2); padding: 0 12px; }
.btn:disabled { opacity: .5; cursor: default; }
button:focus-visible, input:focus-visible { outline: 2px solid var(--fd-a500); outline-offset: 2px; }
.row { display: flex; align-items: center; gap: 10px; min-height: var(--fd-touch); padding: 8px 0; flex-wrap: wrap; }
.row + .row { border-top: 1px solid var(--fd-line); }
.row .who { flex: 1 1 150px; min-width: 0; display: flex; flex-direction: column; }
.row .who b { font-weight: 500; overflow-wrap: anywhere; }
.row .who span { color: var(--fd-t2); font-size: 12px; }
.sw { flex: none; position: relative; width: 48px; height: 28px; border-radius: 14px; border: 1px solid var(--fd-line); background: var(--fd-sunk); padding: 0; }
.sw::after { content: ""; position: absolute; top: 3px; left: 3px; width: 20px; height: 20px; border-radius: 50%; background: var(--fd-t3); transition: transform .15s, background .15s; }
.sw[aria-checked="true"] { background: var(--fd-a700); border-color: var(--fd-a700); }
.sw[aria-checked="true"]::after { transform: translateX(20px); background: #fff; }
.hit { display: inline-flex; align-items: center; min-height: var(--fd-touch); }
input[type=number] { box-sizing: border-box; width: 92px; min-height: var(--fd-touch); padding: 0 10px; border: 1px solid var(--fd-line); border-radius: 10px; background: var(--fd-page); color: var(--fd-t1); font: inherit; text-align: right; }
.chip { display: inline-flex; align-items: center; padding: 1px 9px; border-radius: var(--fd-r-pill); font-size: 11.5px; font-weight: 500; background: var(--fd-a50); color: var(--fd-a900); }
.states { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; margin-bottom: 8px; }
@container (min-width: 520px) { .states { grid-template-columns: repeat(3, 1fr); } }
.states button { min-height: var(--fd-touch); padding: 4px 10px; border: 1px solid var(--fd-line); border-radius: 12px; background: transparent; text-align: left; overflow-wrap: anywhere; }
.states button[aria-checked="true"] { background: var(--fd-a50); border-color: var(--fd-a500); color: var(--fd-a900); font-weight: 500; }
input[type=text] { box-sizing: border-box; width: 110px; min-height: var(--fd-touch); padding: 0 10px; border: 1px solid var(--fd-line); border-radius: 10px; background: var(--fd-page); color: var(--fd-t1); font: inherit; text-align: right; }
.pot.off { opacity: .55; }
.sum { display: flex; justify-content: space-between; gap: 10px; padding: 9px 0; }
.sum + .sum { border-top: 1px solid var(--fd-line); }
.sum span:last-child { color: var(--fd-t2); text-align: right; }
.note { padding: 12px; border-radius: 10px; background: var(--fd-sunk); color: var(--fd-t2); font-size: 13px; margin: 8px 0; }
code { font-size: 12px; background: var(--fd-sunk); padding: 1px 5px; border-radius: 4px; overflow-wrap: anywhere; }
.msg { text-align: center; padding: 40px 14px; color: var(--fd-t2); }
`;

class FdSetup extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._st = null;
    this._idx = 0;
    this._err = "";
    this._busy = false;
    this._loadFailed = false;
    this._paydaySug = null;
    this._potSug = null;
    this._draft = {};
    this._wired = false;
  }

  get hass() { return this._hass; }
  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    window._fd._hass = window._fd._hass || h;
    if (first) this._load();
  }

  get _isAdmin() { return !!(this._hass && this._hass.user && this._hass.user.is_admin); }
  get _step() { return STEPS[this._idx]; }

  async _load() {
    if (!this._isAdmin) return this._render();
    await window._fd.t("setup.title");
    try {
      this._st = await this._hass.callApi("GET", `${DOMAIN}/setup`);
      this._loadFailed = false;
      const cur = STEPS.indexOf(this._st.current_step);
      this._idx = this._st.completed ? 0 : Math.max(0, cur);
      this._draft = {
        notifications: { ...(this._st.notifications || {}) },
        ai: !!this._st.ai_opt_in,
        region: this._initRegion(),
      };
    } catch (e) {
      console.warn("fd-setup: load failed:", e);
      this._loadFailed = true;
    }
    this._render();
    this._enter();
  }

  /** Fetch whatever the freshly entered step needs, then paint it. */
  async _enter() {
    const step = this._step;
    if (step === "payday" && this._paydaySug === null) {
      try { this._paydaySug = (await this._hass.callApi("GET", `${DOMAIN}/setup/payday_suggestions`)).suggestions || []; }
      catch (e) { this._paydaySug = []; }
      this._initPaydays();
    } else if (step === "pots" && this._potSug === null) {
      try {
        this._potSug = ((await this._hass.callApi("GET", `${DOMAIN}/setup/pot_suggestions`)).suggestions || [])
          .map((s) => ({ ...s, on: true, amount: s.cycle_budget }));
      } catch (e) { this._potSug = []; }
    } else if (step === "done") {
      try { this._st = await this._hass.callApi("GET", `${DOMAIN}/setup`); } catch (e) { /* keep last */ }
    }
    if (step === this._step) this._render();
    this.shadowRoot.querySelector("h2")?.focus();
  }

  /** Server value first; otherwise a state hint from hass.config when HA exposes one. */
  _initRegion() {
    const r = this._st.region || {};
    let state = r.state || "";
    if (!state) {
      const cfg = (this._hass && this._hass.config) || {};
      const hint = String(cfg.state || cfg.region || "").toUpperCase();
      if (STATES.some(([c]) => c === hint)) state = hint;
    }
    return { state, postcode: r.postcode || "" };
  }

  _initPaydays() {
    const out = {};
    for (const p of (this._st.persons || [])) {
      const s = (this._paydaySug || []).find((x) => x.person === p.name) || {};
      const own = p.payday && typeof p.payday === "object" ? p.payday.day : p.payday;
      out[p.name] = String(own || s.confirmed_day || s.suggested_day || "");
    }
    this._draft.paydays = out;
  }

  // ---- render -----------------------------------------------------------
  _render() {
    const sh = this.shadowRoot;
    const { escHtml } = window._fd;
    const head = `<style>${window._fd.SHARED_CSS}${CSS}</style>`;
    this.setAttribute("role", "dialog");
    this.setAttribute("aria-modal", "true");
    this.setAttribute("aria-label", tr("setup.title"));
    const closeBtn = `<button type="button" class="btn text" data-a="close">${escHtml(tr("setup.later"))}</button>`;
    if (!this._isAdmin || this._loadFailed || !this._st) {
      const body = !this._isAdmin ? escHtml(tr("setup.admin_only"))
        : this._loadFailed ? `${escHtml(tr("setup.load_error"))}<br><br><button type="button" class="btn" data-a="retry">${escHtml(tr("setup.retry"))}</button>`
        : "…";
      sh.innerHTML = `${head}<div class="root"><div class="top"><span class="lbl">${escHtml(tr("setup.title"))}</span>${closeBtn}</div><div class="msg">${body}</div></div>`;
      this._wire();
      return;
    }
    const step = this._step;
    const last = step === "done";
    const dots = STEPS.map((s, i) => `<li class="${i === this._idx ? "cur" : i < this._idx ? "on" : ""}"${i === this._idx ? ' aria-current="step"' : ""}></li>`).join("");
    const skip = SKIPPABLE.has(step) ? `<button type="button" class="btn text" data-a="skip">${escHtml(tr("setup.skip"))}</button>` : "";
    const foot = last
      ? `<button type="button" class="btn ghost" data-a="back">${escHtml(tr("setup.back"))}</button><span class="sp"></span><button type="button" class="btn" data-a="finish">${escHtml(tr("setup.done.cta"))}</button>`
      : `<button type="button" class="btn ghost" data-a="back"${this._idx === 0 ? " disabled" : ""}>${escHtml(tr("setup.back"))}</button><span class="sp"></span>${skip}<button type="button" class="btn" data-a="next">${escHtml(tr("setup.next"))}</button>`;
    sh.innerHTML = `${head}<div class="root">
  <div class="top"><span class="lbl">${escHtml(tr("setup.title"))} · ${escHtml(tr("setup.step_of", { n: this._idx + 1, total: STEPS.length }))}</span>${closeBtn}</div>
  <ol class="dots" aria-hidden="true">${dots}</ol>
  <main><div class="card" id="body">${this._body(step)}</div><p class="err" id="err" role="alert">${escHtml(this._err)}</p></main>
  <div class="foot"><div>${foot}</div></div></div>`;
    this._mountEmbedded(step);
    this._wire();
  }

  _head(key) {
    const { escHtml } = window._fd;
    return `<h2 tabindex="-1">${escHtml(tr(`setup.${key}.title`))}</h2><p class="muted">${escHtml(tr(`setup.${key}.body`))}</p>`;
  }

  _body(step) {
    const { escHtml } = window._fd;
    const sw = (id, on, label) => `<div class="row"><div class="who"><b>${escHtml(label)}</b></div><span class="hit"><button type="button" class="sw" role="switch" aria-checked="${on}" data-sw="${id}" aria-label="${escHtml(label)}"></button></span></div>`;
    switch (step) {
      case "persons": case "accounts":
        return `${this._head(step)}<div id="embed"></div>`;
      case "payday": return this._paydayBody();
      case "region": return this._regionBody();
      case "pots": return this._potsBody();
      case "plan":
        return `${this._head("plan")}<div class="note">${escHtml(tr("setup.plan.import"))}</div><p class="muted">${escHtml(tr("setup.plan.later"))}</p>`;
      case "notifications": {
        const n = this._draft.notifications || {};
        const detail = n.enabled === false ? "" : `
          ${sw("large_debit", n.large_debit !== false, tr("setup.notif.large_debit"))}
          ${n.large_debit !== false ? `<div class="row"><div class="who"><span>${escHtml(tr("setup.notif.factor"))}</span></div>
            <input type="number" min="1" step="0.5" data-num="large_debit_factor" value="${escHtml(n.large_debit_factor ?? 3)}" aria-label="${escHtml(tr("setup.notif.factor_label"))}"></div>
            <div class="row"><div class="who"><span>${escHtml(tr("setup.notif.threshold"))}</span></div>
            <input type="number" min="0" step="50" data-num="large_debit_threshold" value="${escHtml(n.large_debit_threshold ?? 500)}" aria-label="${escHtml(tr("setup.notif.threshold"))}"></div>` : ""}
          ${sw("double_charge", n.double_charge !== false, tr("setup.notif.double_charge"))}
          ${sw("missing_salary", n.missing_salary !== false, tr("setup.notif.missing_salary"))}
          ${sw("consent_expiring", n.consent_expiring !== false, tr("setup.notif.consent_expiring"))}
          ${sw("digest_enabled", n.digest_enabled !== false, tr("setup.notif.digest_enabled"))}`;
        return `${this._head("notif")}${sw("enabled", n.enabled !== false, tr("setup.notif.enabled"))}${detail}`;
      }
      case "ai":
        return `${this._head("ai")}<div class="note">${escHtml(tr("setup.ai.privacy"))}</div>${sw("ai", !!this._draft.ai, tr("setup.ai.toggle"))}`;
      default: return this._doneBody();
    }
  }

  _paydayBody() {
    const { escHtml } = window._fd;
    const persons = this._st.persons || [];
    if (this._paydaySug === null) return `${this._head("payday")}<p class="muted">…</p>`;
    if (!persons.length) return `${this._head("payday")}<div class="note">${escHtml(tr("setup.payday.no_persons"))}</div>`;
    const rows = persons.map((p) => {
      const s = (this._paydaySug || []).find((x) => x.person === p.name);
      const val = (this._draft.paydays || {})[p.name] ?? "";
      let hint = tr("setup.payday.none");
      if (s && s.suggested_day) {
        const amount = s.amount ? new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(Math.abs(s.amount)) : "";
        hint = s.source && amount ? tr("setup.payday.suggest", { day: s.suggested_day, source: s.source, amount }) : tr("setup.payday.suggest_short", { day: s.suggested_day });
      }
      const confirmed = p.payday && (typeof p.payday === "object" ? p.payday.confirmed : true);
      const use = s && s.suggested_day && String(s.suggested_day) !== String(val)
        ? `<button type="button" class="btn ghost" data-use="${escHtml(p.name)}" data-day="${escHtml(s.suggested_day)}">${escHtml(tr("setup.payday.use"))}</button>` : "";
      return `<div class="row"><div class="who"><b>${escHtml(p.name)}${confirmed ? ` <span class="chip">${escHtml(tr("setup.payday.confirmed"))}</span>` : ""}</b><span>${escHtml(hint)}</span></div>
        ${use}<input type="number" min="1" max="31" step="1" inputmode="numeric" data-day-of="${escHtml(p.name)}" value="${escHtml(val)}" aria-label="${escHtml(tr("setup.payday.day") + ": " + p.name)}"></div>`;
    }).join("");
    return `${this._head("payday")}${rows}`;
  }

  _regionBody() {
    const { escHtml } = window._fd;
    const r = this._draft.region || {};
    const chips = STATES.map(([code, name]) => `<button type="button" role="radio" aria-checked="${r.state === code}" data-state="${code}">${escHtml(name)}</button>`).join("");
    return `${this._head("region")}<div class="states" role="radiogroup" aria-label="${escHtml(tr("setup.region.state"))}">${chips}</div>
      <div class="row"><div class="who"><b>${escHtml(tr("setup.region.postcode"))}</b></div>
      <input type="text" inputmode="numeric" maxlength="5" autocomplete="postal-code" data-postcode value="${escHtml(r.postcode || "")}" aria-label="${escHtml(tr("setup.region.postcode"))}"></div>`;
  }

  _potsBody() {
    const { escHtml } = window._fd;
    if (this._potSug === null) return `${this._head("pots")}<p class="muted">…</p>`;
    if (!this._potSug.length) return `${this._head("pots")}<div class="note">${escHtml(tr("setup.pots.empty"))}</div>`;
    const cats = window._fd.CAT_LABELS || {};
    const rows = this._potSug.map((s, i) => {
      const owner = s.owner === "shared" ? tr("setup.pots.owner_shared") : s.owner;
      const label = s.name || cats[s.category] || s.category;
      return `<div class="row pot ${s.on ? "" : "off"}"><span class="hit"><button type="button" class="sw" role="switch" aria-checked="${s.on}" data-pot="${i}" aria-label="${escHtml(label)}"></button></span>
        <div class="who"><b>${escHtml(label)}</b><span>${escHtml(owner)} · ${escHtml(tr("setup.pots.samples", { n: s.samples }))}</span></div>
        <input type="number" min="0" step="10" inputmode="decimal" data-pot-amt="${i}" value="${escHtml(s.amount)}" aria-label="${escHtml(tr("setup.pots.amount") + ": " + label + " (" + tr("setup.pots.per_cycle") + ")")}"${s.on ? "" : " disabled"}></div>`;
    }).join("");
    return `${this._head("pots")}${rows}`;
  }

  _regionLabel() {
    const r = this._st.region || {};
    const name = (STATES.find(([c]) => c === r.state) || [])[1];
    return name ? `${name}${r.postcode ? ` · ${r.postcode}` : ""}` : tr("setup.status.skipped");
  }

  _doneBody() {
    const { escHtml } = window._fd;
    const st = this._st.steps || {};
    const n = this._st.notifications || {};
    const mark = (k) => escHtml(tr(`setup.status.${st[k] || "pending"}`));
    const persons = (this._st.persons || []);
    const paydays = persons.filter((p) => p.payday).length;
    const rows = [
      ["persons", persons.length ? persons.map((p) => p.name).join(", ") : mark("persons")],
      ["accounts", mark("accounts")],
      ["payday", persons.length ? `${paydays} / ${persons.length}` : mark("payday")],
      ["region", escHtml(this._regionLabel())],
      ["pots", mark("pots")],
      ["plan", mark("plan")],
      ["notifications", escHtml(tr(n.enabled === false ? "setup.status.off" : "setup.status.on"))],
      ["ai", escHtml(tr(this._st.ai_opt_in ? "setup.status.on" : "setup.status.off"))],
    ];
    return `${this._head("done")}${rows.map(([k, v]) => `<div class="sum"><span>${escHtml(tr("setup.summary." + k))}</span><span>${v}</span></div>`).join("")}`;
  }

  /** persons / accounts steps reuse fd-settings in "section" mode (its own Save bar hidden). */
  _mountEmbedded(step) {
    const box = this.shadowRoot.getElementById("embed");
    if (!box) return;
    const el = document.createElement("fd-settings");
    el.setAttribute("section", step);
    el.setAttribute("embedded", "");
    el.hass = this._hass;
    box.append(el);
    this._settingsEl = el;
  }

  // ---- events -----------------------------------------------------------
  _wire() {
    const sh = this.shadowRoot;
    if (this._wired) return;
    this._wired = true;
    sh.addEventListener("click", (ev) => {
      const t = ev.target.closest("button");
      if (!t) return;
      if (t.dataset.a) this._action(t.dataset.a);
      else if (t.dataset.sw) this._toggle(t.dataset.sw);
      else if (t.dataset.pot !== undefined) {
        const s = this._potSug[Number(t.dataset.pot)];
        s.on = !s.on;
        this._render();
      } else if (t.dataset.state) {
        const r = this._draft.region;
        r.state = r.state === t.dataset.state ? "" : t.dataset.state;
        this._render();
      } else if (t.dataset.use) {
        this._draft.paydays[t.dataset.use] = t.dataset.day;
        this._render();
      }
    });
    sh.addEventListener("input", (ev) => {
      const el = ev.target;
      if (el.dataset.dayOf !== undefined) this._draft.paydays[el.dataset.dayOf] = el.value;
      else if (el.dataset.potAmt !== undefined) this._potSug[Number(el.dataset.potAmt)].amount = el.value;
      else if (el.dataset.postcode !== undefined) this._draft.region.postcode = el.value.trim();
      else if (el.dataset.num) this._draft.notifications[el.dataset.num] = el.value === "" ? "" : Number(el.value);
    });
    this.onkeydown = (ev) => { if (ev.key === "Escape") this._close(false); };
  }

  _toggle(id) {
    if (id === "ai") this._draft.ai = !this._draft.ai;
    else {
      const n = this._draft.notifications;
      n[id] = n[id] === false;
    }
    this._render();
  }

  _close(completed) {
    this.dispatchEvent(new CustomEvent("fd-setup-close", { bubbles: true, composed: true, detail: { completed } }));
  }

  _action(a) {
    if (a === "close") this._close(false);
    else if (a === "retry") { this._loadFailed = false; this._load(); }
    else if (a === "back") this._go(this._idx - 1);
    else if (a === "skip") this._advance("skipped");
    else if (a === "next") this._advance("done");
    else if (a === "finish") this._finish();
  }

  _go(i) {
    this._err = "";
    this._idx = Math.min(STEPS.length - 1, Math.max(0, i));
    this._render();
    this._enter();
  }

  _fail(msg) {
    this._err = msg;
    const el = this.shadowRoot.getElementById("err");
    if (el) el.textContent = msg;
  }

  _errText(e) {
    const detail = (e && e.body && (e.body.detail || e.body.error)) || (e && e.message) || "";
    return detail ? `${tr("setup.error")}: ${detail}` : tr("setup.error");
  }

  _put(body) {
    return this._hass.callApi("PUT", `${DOMAIN}/setup`, body);
  }

  /** Store the current step on the server, then move on. skipped never writes the step's data. */
  async _advance(status) {
    if (this._busy) return;
    const step = this._step;
    this._err = "";
    this._busy = true;
    const buttons = this.shadowRoot.querySelectorAll(".foot button");
    buttons.forEach((b) => { b.disabled = true; });
    if (step === "region" && status === "skipped") { this._busy = false; return this._go(this._idx + 1); }
    try {
      if (step === "plan") status = "skipped"; // nothing is imported here; the page only explains the service
      let body = { step, status };
      if (status === "done") {
        if (step === "persons" || step === "accounts") {
          const s = this._settingsEl;
          if (step === "persons" && s && s._draft && !s._draft.persons.length) { this._fail(tr("setup.persons.need_one")); return this._unbusy(); }
          if (s && !(await s.save())) return this._unbusy();
        } else if (step === "payday") {
          const paydays = [];
          for (const [person, v] of Object.entries(this._draft.paydays || {})) {
            if (v === "") continue;
            const day = Number(v);
            if (!Number.isInteger(day) || day < 1 || day > 31) { this._fail(`${person}: ${tr("setup.payday.err")}`); return this._unbusy(); }
            paydays.push({ person, day });
          }
          if (paydays.length) body.paydays = paydays; else body.status = "skipped";
        } else if (step === "region") {
          const r = this._draft.region || {};
          if (r.postcode && !/^\d{5}$/.test(r.postcode)) { this._fail(tr("setup.region.err_postcode")); return this._unbusy(); }
          if (!r.state) { this._busy = false; return this._go(this._idx + 1); }
          this._st = await this._put({ region: { state: r.state, ...(r.postcode ? { postcode: r.postcode } : {}) } });
          this._busy = false;
          return this._go(this._idx + 1);
        } else if (step === "pots") {
          const accept = (this._potSug || []).filter((s) => s.on && Number(s.amount) > 0)
            .map((s) => ({ category: s.category, owner: s.owner, cycle_budget: Number(s.amount), name: s.name }));
          if (accept.length) {
            await this._hass.callApi("POST", `${DOMAIN}/setup/pot_suggestions`, { accept });
            this._potSug = null;
            this._toast(tr("setup.pots.created", { n: accept.length }), "success");
          } else body.status = "skipped";
        } else if (step === "notifications") {
          body.notifications = this._cleanNotifications();
        } else if (step === "ai") {
          body.ai_opt_in = !!this._draft.ai;
        }
      }
      this._st = await this._put(body);
      this._draft.notifications = { ...(this._st.notifications || this._draft.notifications) };
      this._busy = false;
      this._go(this._idx + 1);
    } catch (e) {
      this._fail(this._errText(e));
      this._unbusy();
    }
  }

  _unbusy() {
    this._busy = false;
    this.shadowRoot.querySelectorAll(".foot button").forEach((b) => { b.disabled = this._idx === 0 && b.dataset.a === "back"; });
  }

  _cleanNotifications() {
    const n = { ...this._draft.notifications };
    for (const k of ["large_debit_factor", "large_debit_threshold"]) {
      if (n[k] === "" || n[k] === undefined || Number.isNaN(n[k])) delete n[k];
    }
    return n;
  }

  async _finish() {
    if (this._busy) return;
    this._busy = true;
    try {
      await this._put({ complete: true });
      this._busy = false;
      this._close(true);
    } catch (e) {
      this._busy = false;
      this._fail(this._errText(e));
    }
  }

  _toast(message, type) {
    this.dispatchEvent(new CustomEvent("fd-toast", { bubbles: true, composed: true, detail: { message, type } }));
  }
}

window._fd.defineOnce("fd-setup", FdSetup);
