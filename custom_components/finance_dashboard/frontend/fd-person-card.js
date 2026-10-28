/**
 * fd-person-card — one person's share of the household money (Spielgeld).
 *
 * New design: person colour stripe, a stacked bar showing where the net
 * income goes (household share · own costs · what is left), and a status
 * chip (passt / knapp / drüber) on the remainder. Never red, no guilt tone.
 *
 * Properties:
 *   member     {object}  — Household member data
 *   splitModel {string}  — Current split model name
 *   index      {number}  — optional position, picks the person colour
 */

const PERSON_COLORS = [
  "var(--fd-person-a)", "var(--fd-person-b)", "#5d4037", "#455a64", "#9e9d24",
];

// New texts resolve through the locale files; until a key exists the inline
// default is used (de / en) so the UI never shows a raw key.
function T(key, de, en, vars = {}) {
  const f = window._fd;
  const s = f.tSync(key, vars);
  if (s !== key) return s;
  const raw = ((f._hass && f._hass.language) || navigator.language || "en").toLowerCase();
  let text = raw.startsWith("de") ? de : en;
  for (const [k, v] of Object.entries(vars)) text = text.replace(new RegExp(`\\$${k}`, "g"), String(v));
  return text;
}

class FdPersonCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._member = null;
    this._splitModel = "proportional";
    this._index = 0;
  }

  set member(v) { this._member = v; this._render(); }
  set splitModel(v) { this._splitModel = v; this._render(); }
  set index(v) { this._index = Number(v) || 0; this._render(); }

  _render() {
    const m = this._member;
    if (!m) {
      this.shadowRoot.innerHTML = "";
      return;
    }
    const { SHARED_CSS, escHtml, eur } = window._fd;
    const color = PERSON_COLORS[this._index % PERSON_COLORS.length];

    const splitLabel = this._splitModel === "proportional" ? T("hh.split.proportional", "Nach Einkommen", "By income")
      : this._splitModel === "equal" ? T("hh.split.equal", "Zu gleichen Teilen", "Equal parts")
        : T("hh.split.custom", "Eigene Verteilung", "Custom split");

    const net = Math.max(m.net_income || 0, 0);
    const left = m.spielgeld || 0;
    // Status on what is left of the net income: relaxed >= 15 %, tight >= 5 %.
    const frac = net > 0 ? left / net : (left >= 0 ? 1 : -1);
    const st = frac >= 0.15 ? "ok" : frac >= 0.05 ? "near" : "over";
    const stLabel = st === "ok" ? T("hh.status.ok", "passt", "fine")
      : st === "near" ? T("hh.status.near", "knapp", "tight") : T("hh.status.over", "drüber", "over");

    const seg = (v) => (net > 0 ? Math.max(0, Math.min(100, (v / net) * 100)) : 0);
    const wShared = seg(m.shared_costs_share);
    const wOwn = seg(m.individual_costs);
    const wLeft = Math.max(0, 100 - wShared - wOwn);

    const bonus = m.bonus_amount > 0
      ? `<li><span>${T("hh.person.bonus", "Bonus (erkannt)", "Bonus (detected)")}</span><b>${eur(m.bonus_amount)}</b></li>` : "";

    const LOCAL_CSS = `
:host { display: block; }
.person { position: relative; padding: 14px 16px 14px 20px; border-radius: var(--fd-r-card); background: var(--fd-card); box-shadow: var(--fd-sh1); overflow: hidden; }
.person::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 6px; background: ${color}; }
.head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.name { display: flex; align-items: center; gap: 8px; font-size: 16px; font-weight: 500; min-width: 0; }
.name i { flex: none; width: 10px; height: 10px; border-radius: 50%; background: ${color}; }
.name span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chip { display: inline-flex; align-items: center; padding: 1px 10px; border-radius: var(--fd-r-pill); font-size: 11.5px; font-weight: 500; white-space: nowrap; background: var(--cbg); color: var(--cfg); }
.st-ok { --c: var(--fd-ok); --cbg: var(--fd-ok-bg); --cfg: color-mix(in srgb, var(--fd-ok) 72%, var(--fd-t1)); }
.st-near { --c: var(--fd-near); --cbg: var(--fd-near-bg); --cfg: color-mix(in srgb, var(--fd-near) 72%, var(--fd-t1)); }
.st-over { --c: var(--fd-over); --cbg: var(--fd-over-bg); --cfg: color-mix(in srgb, var(--fd-over) 72%, var(--fd-t1)); }
.left { margin: 10px 0 2px; font-size: 30px; font-weight: 500; line-height: 1.05; color: var(--cfg); }
.cap { font-size: 12px; color: var(--fd-t2); }
.bar { display: flex; height: 12px; margin: 12px 0 6px; border-radius: 6px; overflow: hidden; background: var(--fd-sunk); }
.bar i { display: block; height: 100%; }
.legend { display: flex; flex-wrap: wrap; gap: 2px 12px; font-size: 11px; color: var(--fd-t2); }
.legend i { display: inline-block; width: 8px; height: 8px; margin-right: 4px; border-radius: 50%; }
.rows { list-style: none; margin: 10px 0 0; padding: 0; font-size: 13px; }
.rows li { display: flex; justify-content: space-between; gap: 8px; padding: 7px 0; }
.rows li + li { border-top: 1px solid var(--fd-line); }
.rows li span { color: var(--fd-t2); }
.rows li b { font-weight: 500; white-space: nowrap; }
`;

    this.shadowRoot.innerHTML = `
<style>${SHARED_CSS}${LOCAL_CSS}</style>
<div class="person st-${st}">
  <div class="head">
    <div class="name"><i></i><span>${escHtml(m.person)}</span></div>
    <span class="chip">${escHtml(stLabel)}</span>
  </div>
  <div class="left">${eur(left)}</div>
  <div class="cap">${T("hh.person.left", "bleibt zur freien Verfügung", "left to spend freely")} · ${escHtml(splitLabel)} · ${(m.income_ratio || 0).toFixed(0)} %</div>
  <div class="bar" role="img" aria-label="${T("hh.person.bar", "Verteilung des Nettoeinkommens", "How the net income is used")}">
    <i style="width:${wShared}%;background:var(--fd-household)"></i>
    <i style="width:${wOwn}%;background:${color}"></i>
    <i style="width:${wLeft}%;background:var(--c)"></i>
  </div>
  <div class="legend">
    <span><i style="background:var(--fd-household)"></i>${T("hh.person.share", "Haushalt", "Household")}</span>
    <span><i style="background:${color}"></i>${T("hh.person.own", "Eigene", "Own")}</span>
    <span><i style="background:var(--c)"></i>${T("hh.person.free", "Frei", "Free")}</span>
  </div>
  <ul class="rows">
    <li><span>${T("hh.person.income", "Einkommen (netto)", "Income (net)")}</span><b>${eur(m.net_income)}</b></li>
    <li><span>${T("hh.person.shared", "Anteil gemeinsame Fixkosten", "Share of shared fixed costs")}</span><b>${eur(m.shared_costs_share)}</b></li>
    <li><span>${T("hh.person.individual", "Eigene Ausgaben", "Own expenses")}</span><b>${eur(m.individual_costs)}</b></li>
    ${bonus}
  </ul>
</div>`;
  }
}

window._fd.defineOnce("fd-person-card", FdPersonCard);
