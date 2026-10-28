/**
 * fd-household-section — mine / yours / ours.
 *
 * One card per person (own colour, what is left after the household share)
 * plus the "ours" card: the shared fixed costs everybody can see and how they
 * are split. Optimised for two persons, works for N.
 *
 * Renders conditionally: only visible when household data is present.
 *
 * Properties:
 *   data {object} — Unified data object from fd-data-provider
 *
 * Side channel: the latest data object is published as window._fd._actual and
 * announced with a window "fd-actual-data" event, so fd-budget-plan can set the
 * plan against the bank-derived actuals without owning a second data path.
 */

const PERSON_COLORS = [
  "var(--fd-person-a)", "var(--fd-person-b)", "#5d4037", "#455a64", "#9e9d24",
];

function T(key, de, en, vars = {}) {
  const f = window._fd;
  const s = f.tSync(key, vars);
  if (s !== key) return s;
  const raw = ((f._hass && f._hass.language) || navigator.language || "en").toLowerCase();
  let text = raw.startsWith("de") ? de : en;
  for (const [k, v] of Object.entries(vars)) text = text.replace(new RegExp(`\\$${k}`, "g"), String(v));
  return text;
}

class FdHouseholdSection extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
  }

  set data(v) {
    this._data = v;
    if (window._fd) {
      window._fd._actual = v;
      window.dispatchEvent(new CustomEvent("fd-actual-data"));
    }
    this._render();
  }

  _render() {
    const d = this._data;
    const household = d?.household;
    if (!household || !household.members || household.members.length === 0) {
      this.shadowRoot.innerHTML = "";
      return;
    }

    const { SHARED_CSS, escHtml, eur } = window._fd;
    const members = household.members;
    const total = household.total_shared_costs || 0;

    const LOCAL_CSS = `
:host { display: block; margin-bottom: 14px; }
.root { container: hh / inline-size; color: var(--fd-t1); font-size: 13px; line-height: 1.4; }
.sect { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin: 0 2px 8px; font-size: 14px; font-weight: 500; }
.sect small { font-size: 11.5px; font-weight: 400; color: var(--fd-t2); }
.persons { display: grid; grid-template-columns: 1fr; gap: 12px; margin-bottom: 12px; }
@container hh (min-width: 640px) { .persons { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); } }
.ours { position: relative; padding: 14px 16px 14px 20px; border-radius: var(--fd-r-card); background: var(--fd-card); box-shadow: var(--fd-sh1); overflow: hidden; }
.ours::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 6px; background: var(--fd-household); }
.ours .head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.ours .name { display: flex; align-items: center; gap: 8px; font-size: 16px; font-weight: 500; }
.ours .name i { width: 10px; height: 10px; border-radius: 50%; background: var(--fd-household); }
.ours .big { margin: 8px 0 2px; font-size: 30px; font-weight: 500; line-height: 1.05; }
.cap { font-size: 12px; color: var(--fd-t2); }
.bar { display: flex; height: 12px; margin: 12px 0 8px; border-radius: 6px; overflow: hidden; background: var(--fd-sunk); }
.bar div { height: 100%; }
.legend { display: grid; grid-template-columns: 1fr; gap: 4px 16px; }
@container hh (min-width: 560px) { .legend { grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); } }
.legend div { display: flex; align-items: center; gap: 6px; min-width: 0; }
.legend i { flex: none; width: 8px; height: 8px; border-radius: 50%; }
.legend span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.legend b { margin-left: auto; font-weight: 500; white-space: nowrap; }
.legend em { font-style: normal; color: var(--fd-t2); font-size: 11.5px; }
`;

    const bar = members.map((m, i) => {
      const w = total > 0 ? (m.shared_costs_share / total * 100) : 0;
      return `<div style="width:${w}%;background:${PERSON_COLORS[i % PERSON_COLORS.length]}"></div>`;
    }).join("");
    const legend = members.map((m, i) => `
<div><i style="background:${PERSON_COLORS[i % PERSON_COLORS.length]}"></i>
  <span>${escHtml(m.person)} <em>${(m.income_ratio || 0).toFixed(0)} %</em></span>
  <b>${eur(m.shared_costs_share)}</b></div>`).join("");

    const ours = total > 0 ? `
<div class="ours">
  <div class="head">
    <div class="name"><i></i>${T("hh.ours.title", "Gemeinsam", "Ours")}</div>
  </div>
  <div class="big">${eur(total)}</div>
  <div class="cap">${T("hh.ours.cap", "gemeinsame Fixkosten im Monat – für alle sichtbar", "shared fixed costs per month – visible to everyone")}</div>
  <div class="bar" role="img" aria-label="${T("hh.ours.split", "Aufteilung der gemeinsamen Fixkosten", "How the shared fixed costs are split")}">${bar}</div>
  <div class="legend">${legend}</div>
</div>` : "";

    this.shadowRoot.innerHTML = `
<style>${SHARED_CSS}${LOCAL_CSS}</style>
<div class="root">
  <div class="sect">${T("hh.section.title", "Meins · Deins · Unseres", "Mine · Yours · Ours")}
    <small>${T("hh.section.sub", "Was nach dem Haushalt übrig bleibt", "What is left after the household")}</small></div>
  <div class="persons" id="persons"></div>
  ${ours}
</div>`;

    const personsEl = this.shadowRoot.getElementById("persons");
    members.forEach((m, i) => {
      const card = document.createElement("fd-person-card");
      card.index = i;
      card.member = m;
      card.splitModel = household.split_model || "proportional";
      personsEl.appendChild(card);
    });
  }
}

window._fd.defineOnce("fd-household-section", FdHouseholdSection);
