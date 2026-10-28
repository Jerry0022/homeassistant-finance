/**
 * fd-settings — "Personen & Konten" (admin only; renders nothing otherwise).
 *
 *   GET/PUT finance_dashboard/assignments
 *     {persons:[{name, ha_users:[id]}],
 *      ha_users:[{id,name,is_admin,suggested,reason}],
 *      accounts:[{key,name,institution,iban_last4,owner:"<person>"|"shared"|""}],
 *      plan_persons:[names]}
 *   PUT body: {persons:[{name,ha_users}], accounts:[{key,owner}]}
 *
 * Step 1 "Wer gehört zum Haushalt?" — HA users become persons (name editable).
 * Step 2 "Welches Konto gehört wem?" — segmented choice per account.
 *
 * Properties: hass (required), data (optional pre-loaded payload from fd-overview).
 * Events (bubbling, composed):
 *   fd-toast              {message, type}   — panel routes it to fd-header.showToast()
 *   fd-assignments-saved  {payload}         — Start / Overview reload
 */

const DOMAIN = "finance_dashboard";

// Fallback texts: used until locales/*.json carry the settings.* keys.
const FB = {
  de: {
    "settings.title": "Personen & Konten",
    "settings.intro": "Lege fest, wer zum Haushalt gehört und welchem Konto wer zugeordnet ist. Die Zuordnung ist nur der Standard – Budgetposten und Korrekturen gehen vor.",
    "settings.step1": "Wer gehört zum Haushalt?",
    "settings.step1_hint": "Jeder Home-Assistant-Benutzer, der zum Haushalt gehört, wird zu einer Person.",
    "settings.user_toggle": "Gehört zum Haushalt",
    "settings.suggested": "Vorgeschlagen",
    "settings.admin": "Admin",
    "settings.reason.person": "Bereits Person",
    "settings.reason.active_user": "Aktiver Benutzer",
    "settings.reason.system": "Systembenutzer",
    "settings.reason.inactive": "Inaktiv",
    "settings.reason.no_person": "Keine Person in Home Assistant",
    "settings.more_users": "Weitere Benutzer ($n)",
    "settings.person_name": "Name der Person",
    "settings.person_remove": "Person entfernen",
    "settings.persons_free": "Personen ohne Benutzer",
    "settings.plan_persons": "Aus dem Budgetplan",
    "settings.add_person": "Person hinzufügen",
    "settings.step2": "Welches Konto gehört wem?",
    "settings.step2_hint": "Offen heißt: noch nicht entschieden. Haushalt = gemeinsames Konto.",
    "settings.owner_shared": "Haushalt",
    "settings.owner_none": "Offen",
    "settings.no_accounts": "Noch keine Konten verbunden.",
    "settings.no_persons": "Lege zuerst oben mindestens eine Person fest.",
    "settings.save": "Speichern",
    "settings.saving": "Speichere…",
    "settings.saved": "Zuordnung gespeichert",
    "settings.error": "Speichern fehlgeschlagen",
    "settings.err_name": "Jede Person braucht einen Namen.",
    "settings.err_dup": "Jeder Name darf nur einmal vorkommen.",
    "settings.load_error": "Zuordnung konnte nicht geladen werden.",
  },
  en: {
    "settings.title": "People & accounts",
    "settings.intro": "Decide who belongs to the household and which account belongs to whom. This is only the default – budget positions and corrections take precedence.",
    "settings.step1": "Who is part of the household?",
    "settings.step1_hint": "Every Home Assistant user who belongs to the household becomes a person.",
    "settings.user_toggle": "Part of the household",
    "settings.suggested": "Suggested",
    "settings.admin": "Admin",
    "settings.reason.person": "Already a person",
    "settings.reason.active_user": "Active user",
    "settings.reason.system": "System user",
    "settings.reason.inactive": "Inactive",
    "settings.reason.no_person": "No person in Home Assistant",
    "settings.more_users": "More users ($n)",
    "settings.person_name": "Person name",
    "settings.person_remove": "Remove person",
    "settings.persons_free": "People without a user",
    "settings.plan_persons": "From the budget plan",
    "settings.add_person": "Add person",
    "settings.step2": "Which account belongs to whom?",
    "settings.step2_hint": "Open means not decided yet. Household = shared account.",
    "settings.owner_shared": "Household",
    "settings.owner_none": "Open",
    "settings.no_accounts": "No accounts connected yet.",
    "settings.no_persons": "Add at least one person above first.",
    "settings.save": "Save",
    "settings.saving": "Saving…",
    "settings.saved": "Assignment saved",
    "settings.error": "Saving failed",
    "settings.err_name": "Every person needs a name.",
    "settings.err_dup": "Each name may appear only once.",
    "settings.load_error": "Could not load the assignment.",
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

const PERSON_COLORS = ["var(--fd-person-a)", "var(--fd-person-b)", "#ef6c00", "#5e35b1", "#6d4c41"];

const CSS = `
:host { display: block; }
.root { color: var(--fd-t1); font-size: 13px; line-height: 1.4; }
button { font: inherit; color: inherit; cursor: pointer; }
.card { padding: 14px; border-radius: var(--fd-r-card); background: var(--fd-card); box-shadow: var(--fd-sh1); }
h3 { margin: 0 0 2px; font-size: 16px; font-weight: 500; }
h4 { margin: 18px 0 2px; font-size: 14px; font-weight: 500; }
.muted { color: var(--fd-t2); font-size: 11.5px; margin: 0 0 8px; }
.row { display: flex; align-items: center; gap: 10px; min-height: var(--fd-touch); padding: 6px 0; flex-wrap: wrap; }
.row + .row { border-top: 1px solid var(--fd-line); }
.row .who { flex: 1 1 140px; min-width: 0; display: flex; flex-direction: column; }
.row .who b { font-weight: 500; overflow-wrap: anywhere; }
.row .who span { color: var(--fd-t2); font-size: 11.5px; }
.chip { display: inline-flex; align-items: center; padding: 1px 9px; border-radius: var(--fd-r-pill); font-size: 11.5px; font-weight: 500; background: var(--fd-a50); color: var(--fd-a900); margin-left: 6px; }
.sw { flex: none; position: relative; width: 48px; height: 28px; border-radius: 14px; border: 1px solid var(--fd-line); background: var(--fd-sunk); padding: 0; }
.sw::after { content: ""; position: absolute; top: 3px; left: 3px; width: 20px; height: 20px; border-radius: 50%; background: var(--fd-t3); transition: transform .15s, background .15s; }
.sw[aria-checked="true"] { background: var(--fd-a700); border-color: var(--fd-a700); }
.sw[aria-checked="true"]::after { transform: translateX(20px); background: #fff; }
.hit { position: relative; display: inline-flex; align-items: center; min-height: var(--fd-touch); }
input[type=text] { box-sizing: border-box; flex: 1 1 160px; min-width: 0; min-height: var(--fd-touch); padding: 0 12px; border: 1px solid var(--fd-line); border-radius: 10px; background: var(--fd-page); color: var(--fd-t1); font: inherit; }
.btn { min-height: var(--fd-touch); padding: 0 16px; border: 1px solid transparent; border-radius: var(--fd-r-pill); background: var(--fd-a700); color: #fff; font-weight: 500; }
.btn.ghost { background: transparent; color: var(--fd-a700); border-color: var(--fd-a100); }
.btn.sm { min-height: 36px; padding: 0 12px; font-size: 12px; }
.btn:disabled { opacity: .5; cursor: default; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 0; }
.chips button { min-height: 36px; padding: 0 14px; border: 1px dashed var(--fd-a300); border-radius: var(--fd-r-pill); background: transparent; color: var(--fd-a700); }
details { margin-top: 8px; }
summary { min-height: var(--fd-touch); display: flex; align-items: center; color: var(--fd-t2); cursor: pointer; }
.acc { padding: 8px 0; }
.acc + .acc { border-top: 1px solid var(--fd-line); }
.acc .nm { overflow-wrap: anywhere; }
.acc .nm b { font-weight: 500; }
.acc .nm span { display: block; color: var(--fd-t2); font-size: 11.5px; }
.seg { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.seg button { min-height: 40px; padding: 0 14px; border: 1px solid var(--fd-line); border-radius: var(--fd-r-pill); background: transparent; display: inline-flex; align-items: center; gap: 6px; }
.seg button i { width: 8px; height: 8px; border-radius: 50%; background: var(--c, var(--fd-t3)); }
.seg button[aria-checked="true"] { background: var(--fd-a50); border-color: var(--c, var(--fd-a500)); color: var(--fd-a900); font-weight: 500; }
.bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 10px; margin-top: 16px; }
.err { margin-right: auto; color: var(--fd-over); font-size: 12px; }
button:focus-visible, input:focus-visible, summary:focus-visible { outline: 2px solid var(--fd-a500); outline-offset: 2px; }
.row input[type=text] { order: 3; flex: 1 1 100%; }
@container (min-width: 700px) {
  .row input[type=text] { order: 0; flex: 1 1 200px; max-width: 280px; }
  .acc { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
  .acc .seg { margin-top: 0; justify-content: flex-end; }
}
`;

class FdSettings extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._data = null;
    this._draft = null;
    this._error = "";
    this._saving = false;
    this._loadFailed = false;
  }

  get hass() { return this._hass; }
  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    if (first && !this._data) this.load();
    else if (first) this._render();
  }

  get data() { return this._data; }
  set data(d) {
    this._data = d || null;
    this._draft = d ? this._makeDraft(d) : null;
    this._render();
  }

  get _isAdmin() {
    return !!(this._hass && this._hass.user && this._hass.user.is_admin);
  }

  async load() {
    if (!this._hass || !this._isAdmin) return this._render();
    await window._fd.t("settings.title");
    try {
      this.data = await this._hass.callApi("GET", `${DOMAIN}/assignments`);
      this._loadFailed = false;
    } catch (e) {
      console.warn("fd-settings: load failed:", e);
      this._loadFailed = true;
      this._render();
    }
  }

  _makeDraft(d) {
    return {
      persons: (d.persons || []).map((p) => ({ name: p.name, ha_users: [...(p.ha_users || [])] })),
      owners: Object.fromEntries((d.accounts || []).map((a) => [a.key, a.owner || ""])),
    };
  }

  _personOf(userId) {
    return this._draft.persons.find((p) => p.ha_users.includes(userId));
  }

  _toggleUser(u) {
    const p = this._personOf(u.id);
    if (p) {
      p.ha_users = p.ha_users.filter((x) => x !== u.id);
      if (!p.ha_users.length) this._removePerson(p);
    } else {
      this._draft.persons.push({ name: u.name, ha_users: [u.id] });
    }
  }

  _removePerson(p) {
    this._draft.persons = this._draft.persons.filter((x) => x !== p);
    for (const k of Object.keys(this._draft.owners)) {
      if (this._draft.owners[k] === p.name) this._draft.owners[k] = "";
    }
  }

  _color(name) {
    const i = this._draft.persons.findIndex((p) => p.name === name);
    return PERSON_COLORS[(i < 0 ? 0 : i) % PERSON_COLORS.length];
  }

  _render() {
    const sh = this.shadowRoot;
    if (!this._isAdmin) { sh.innerHTML = ""; return; }
    const { escHtml } = window._fd;
    if (!this._draft) {
      sh.innerHTML = `<style>${window._fd.SHARED_CSS}${CSS}</style><div class="root"><div class="card">
        <h3>${escHtml(tr("settings.title"))}</h3>
        ${this._loadFailed ? `<p class="muted">${escHtml(tr("settings.load_error"))}</p>` : ""}</div></div>`;
      return;
    }
    const d = this._data;
    const users = d.ha_users || [];
    const main = users.filter((u) => u.suggested || this._personOf(u.id));
    const more = users.filter((u) => !main.includes(u));
    const free = this._draft.persons.filter((p) => !p.ha_users.length);
    const planChips = (d.plan_persons || []).filter((n) => !this._draft.persons.some((p) => p.name === n));

    sh.innerHTML = `<style>${window._fd.SHARED_CSS}${CSS}</style>
<div class="root" style="container: settings / inline-size"><div class="card">
  <h3>${escHtml(tr("settings.title"))}</h3>
  <p class="muted">${escHtml(tr("settings.intro"))}</p>
  <h4>1 · ${escHtml(tr("settings.step1"))}</h4>
  <p class="muted">${escHtml(tr("settings.step1_hint"))}</p>
  <div id="users">${main.map((u) => this._userRow(u)).join("")}</div>
  ${more.length ? `<details><summary>${escHtml(tr("settings.more_users", { n: more.length }))}</summary>${more.map((u) => this._userRow(u)).join("")}</details>` : ""}
  ${free.length ? `<h4>${escHtml(tr("settings.persons_free"))}</h4>${free.map((p) => this._freeRow(p)).join("")}` : ""}
  ${planChips.length ? `<p class="muted" style="margin-top:12px">${escHtml(tr("settings.plan_persons"))}</p>
    <div class="chips">${planChips.map((n) => `<button type="button" data-plan="${escHtml(n)}">+ ${escHtml(n)}</button>`).join("")}</div>` : ""}
  <div class="chips"><button type="button" id="addp">+ ${escHtml(tr("settings.add_person"))}</button></div>
  <h4>2 · ${escHtml(tr("settings.step2"))}</h4>
  <p class="muted">${escHtml(tr("settings.step2_hint"))}</p>
  <div id="accts"></div>
  <div class="bar"><span class="err" id="err" role="alert">${escHtml(this._error)}</span>
    <button type="button" class="btn" id="save">${escHtml(tr("settings.save"))}</button></div>
</div></div>`;
    this._renderAccounts();
    if (!this._wired) { this._wired = true; this._wire(); }
  }

  _userRow(u) {
    const { escHtml } = window._fd;
    const p = this._personOf(u.id);
    const on = !!p;
    const reason = tr(`settings.reason.${u.reason || "active_user"}`);
    return `<div class="row" data-user="${escHtml(u.id)}">
  <div class="who"><b>${escHtml(u.name)}${u.is_admin ? `<span class="chip">${escHtml(tr("settings.admin"))}</span>` : ""}</b>
    <span>${escHtml(u.suggested ? tr("settings.suggested") + " · " : "")}${escHtml(reason)}</span></div>
  ${on ? `<input type="text" data-name="${escHtml(u.id)}" value="${escHtml(p.name)}" aria-label="${escHtml(tr("settings.person_name"))}">` : ""}
  <span class="hit"><button type="button" class="sw" role="switch" aria-checked="${on}" data-sw="${escHtml(u.id)}"
    aria-label="${escHtml(tr("settings.user_toggle") + ": " + u.name)}" data-tip="${escHtml(tr("settings.user_toggle"))}"></button></span>
</div>`;
  }

  _freeRow(p) {
    const { escHtml } = window._fd;
    const i = this._draft.persons.indexOf(p);
    return `<div class="row">
  <input type="text" data-free="${i}" value="${escHtml(p.name)}" aria-label="${escHtml(tr("settings.person_name"))}">
  <button type="button" class="btn ghost sm" data-rm="${i}">${escHtml(tr("settings.person_remove"))}</button>
</div>`;
  }

  _renderAccounts() {
    const { escHtml } = window._fd;
    const box = this.shadowRoot.getElementById("accts");
    if (!box) return;
    const accounts = this._data.accounts || [];
    if (!accounts.length) { box.innerHTML = `<p class="muted">${escHtml(tr("settings.no_accounts"))}</p>`; return; }
    const persons = this._draft.persons;
    // Suggested users that are not persons yet are offered right here:
    // picking one makes them a person, so nobody has to do step 1 first.
    const candidates = (this._data.ha_users || []).filter((u) => u.suggested && !this._personOf(u.id));
    const note = persons.length || candidates.length ? "" : `<p class="muted">${escHtml(tr("settings.no_persons"))}</p>`;
    box.innerHTML = note + accounts.map((a) => {
      const cur = this._draft.owners[a.key] || "";
      const opt = (val, label, color) =>
        `<button type="button" role="radio" aria-checked="${cur === val}" data-acc="${escHtml(a.key)}" data-owner="${escHtml(val)}" style="--c:${color}"><i></i>${escHtml(label)}</button>`;
      const opts = persons.map((p) => opt(p.name, p.name, this._color(p.name)))
        .concat(candidates.map((u, i) => opt(`user:${u.id}`, u.name, PERSON_COLORS[(persons.length + i) % PERSON_COLORS.length])))
        .concat([opt("shared", tr("settings.owner_shared"), "var(--fd-household)"), opt("", tr("settings.owner_none"), "var(--fd-t3)")]);
      return `<div class="acc"><div class="nm"><b>${escHtml(a.name)}</b><span>${escHtml(a.institution || "")}${a.iban_last4 ? ` · ••${escHtml(a.iban_last4)}` : ""}</span></div>
  <div class="seg" role="radiogroup" aria-label="${escHtml(a.name)}">${opts.join("")}</div></div>`;
    }).join("");
  }

  _wire() {
    const sh = this.shadowRoot;
    sh.addEventListener("click", (ev) => {
      const t = ev.target.closest("button");
      if (!t) return;
      if (t.dataset.sw) {
        const u = (this._data.ha_users || []).find((x) => x.id === t.dataset.sw);
        if (u) { this._toggleUser(u); this._render(); }
      } else if (t.dataset.plan) {
        this._draft.persons.push({ name: t.dataset.plan, ha_users: [] });
        this._render();
      } else if (t.id === "addp") {
        this._draft.persons.push({ name: "", ha_users: [] });
        this._render();
        const inputs = sh.querySelectorAll("[data-free]");
        inputs[inputs.length - 1]?.focus();
      } else if (t.dataset.rm !== undefined) {
        this._removePerson(this._draft.persons[Number(t.dataset.rm)]);
        this._render();
      } else if (t.dataset.acc && t.dataset.owner.startsWith("user:")) {
        const u = (this._data.ha_users || []).find((x) => `user:${x.id}` === t.dataset.owner);
        if (!u) return;
        if (!this._personOf(u.id)) this._toggleUser(u);
        this._draft.owners[t.dataset.acc] = this._personOf(u.id).name;
        this._render();
      } else if (t.dataset.acc) {
        this._draft.owners[t.dataset.acc] = t.dataset.owner;
        this._renderAccounts();
      } else if (t.id === "save") {
        this._save();
      }
    });
    sh.addEventListener("input", (ev) => {
      const el = ev.target;
      let person = null;
      if (el.dataset.name) person = this._personOf(el.dataset.name);
      else if (el.dataset.free !== undefined) person = this._draft.persons[Number(el.dataset.free)];
      if (!person) return;
      const old = person.name;
      person.name = el.value;
      for (const k of Object.keys(this._draft.owners)) if (this._draft.owners[k] === old) this._draft.owners[k] = el.value;
      this._renderAccounts();
    });
  }

  _fail(msg) {
    this._error = msg;
    const el = this.shadowRoot.getElementById("err");
    if (el) el.textContent = msg;
    this._toast(msg, "error");
  }

  _toast(message, type) {
    this.dispatchEvent(new CustomEvent("fd-toast", { bubbles: true, composed: true, detail: { message, type } }));
  }

  async _save() {
    if (this._saving) return;
    const names = this._draft.persons.map((p) => p.name.trim());
    if (names.some((n) => !n)) return this._fail(tr("settings.err_name"));
    if (new Set(names.map((n) => n.toLowerCase())).size !== names.length) return this._fail(tr("settings.err_dup"));
    const body = {
      persons: this._draft.persons.map((p) => ({ name: p.name.trim(), ha_users: p.ha_users })),
      accounts: (this._data.accounts || []).map((a) => ({
        key: a.key,
        owner: (this._draft.owners[a.key] || "").trim(),
      })),
    };
    this._saving = true;
    const btn = this.shadowRoot.getElementById("save");
    if (btn) { btn.disabled = true; btn.textContent = tr("settings.saving"); }
    try {
      const resp = await this._hass.callApi("PUT", `${DOMAIN}/assignments`, body);
      this._error = "";
      this._saving = false;
      this.data = resp;
      this._toast(tr("settings.saved"), "success");
      this.dispatchEvent(new CustomEvent("fd-assignments-saved", { bubbles: true, composed: true, detail: { payload: resp } }));
    } catch (e) {
      this._saving = false;
      const detail = (e && e.body && (e.body.detail || e.body.error)) || (e && e.message) || "";
      if (btn) { btn.disabled = false; btn.textContent = tr("settings.save"); }
      this._fail(detail ? `${tr("settings.error")}: ${detail}` : tr("settings.error"));
    }
  }
}

window._fd.defineOnce("fd-settings", FdSettings);
