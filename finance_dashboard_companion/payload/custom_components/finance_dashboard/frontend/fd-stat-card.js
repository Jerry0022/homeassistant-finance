/**
 * fd-stat-card — Single KPI card (reusable).
 *
 * Properties:
 *   label    {string}  — KPI label (e.g. "Gesamtsaldo")
 *   value    {string}  — Formatted value (e.g. "1.234,56 EUR")
 *   subtitle {string}  — Detail line (e.g. "2 Konten")
 *   accent   {string}  — Top border color (CSS color)
 *   valclass {string}  — CSS class for value ("pos", "neg", "neu", or custom color style)
 */

class FdStatCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._props = {};
  }

  static get observedAttributes() {
    return ["label", "value", "subtitle", "accent", "valclass"];
  }

  attributeChangedCallback(name, _, val) {
    this._props[name] = val;
    this._render();
  }

  set label(v) { this._props.label = v; this._render(); }
  set value(v) { this._props.value = v; this._render(); }
  set subtitle(v) { this._props.subtitle = v; this._render(); }
  set accent(v) { this._props.accent = v; this._render(); }
  set valclass(v) { this._props.valclass = v; this._render(); }

  _render() {
    const { label = "", value = "", subtitle = "", accent = "var(--ac)", valclass = "" } = this._props;
    this.shadowRoot.innerHTML = `
<style>
:host {
  --sf: var(--card-background-color, #12121a);
  --bd: rgba(255,255,255,0.06);
  --tx: var(--primary-text-color, #e0e0e0);
  --tx2: var(--secondary-text-color, #9898a8);
  --ac: var(--accent-color, #4ecca3);
  --dg: #e74c3c;
  --r: 14px;
  display: block;
}
.stat {
  background: var(--sf);
  border: 1px solid var(--bd);
  border-radius: var(--r);
  padding: 18px;
  position: relative;
  overflow: hidden;
}
.stat::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: ${accent};
}
.label {
  font-size: 11px;
  font-weight: 500;
  color: var(--tx2);
  text-transform: uppercase;
  letter-spacing: .5px;
  margin-bottom: 6px;
}
.value {
  font-size: 26px;
  font-weight: 700;
  line-height: 1;
  margin-bottom: 4px;
}
.subtitle { font-size: 11px; }
.pos { color: var(--ac); }
.neg { color: var(--dg); }
.neu { color: var(--tx2); }
</style>
<div class="stat">
  <div class="label">${this._esc(label)}</div>
  <div class="value ${valclass}">${this._esc(value)}</div>
  <div class="subtitle neu">${this._esc(subtitle)}</div>
</div>`;
  }

  _esc(s) {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }
}

customElements.define("fd-stat-card", FdStatCard);
