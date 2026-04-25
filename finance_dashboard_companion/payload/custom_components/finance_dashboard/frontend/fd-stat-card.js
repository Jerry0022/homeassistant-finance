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
    this._loading = false;
  }

  static get observedAttributes() {
    return ["label", "value", "subtitle", "accent", "valclass"];
  }

  attributeChangedCallback(name, _, val) {
    this._props[name] = val;
    this._render();
  }

  set label(v) { this._props.label = v; this._render(); }
  set value(v) {
    this._loading = (v === null || v === undefined);
    this._props.value = v;
    this._render();
  }
  set subtitle(v) { this._props.subtitle = v; this._render(); }
  set accent(v) { this._props.accent = v; this._render(); }
  set valclass(v) { this._props.valclass = v; this._render(); }

  setData(data) {
    this._loading = (data === null || data === undefined);
    this._render();
  }

  disconnectedCallback() {
    // No timers or observers to clean up in this component.
  }

  _render() {
    const { SHARED_CSS, escHtml } = window._fd;
    const { label = "", value = "", subtitle = "", accent = "var(--ac)", valclass = "" } = this._props;

    const LOCAL_CSS = `
:host {
  /* display:block inherited from SHARED_CSS */
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
/* Skeleton shimmer */
@keyframes fd-shimmer {
  0%   { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}
.skeleton-line {
  border-radius: 4px;
  background: linear-gradient(90deg, var(--sf2) 25%, rgba(255,255,255,0.06) 50%, var(--sf2) 75%);
  background-size: 800px 100%;
  animation: fd-shimmer 1.4s infinite linear;
}
.skeleton-value {
  height: 26px;
  width: 70%;
  margin-bottom: 6px;
}
.skeleton-sub {
  height: 11px;
  width: 45%;
}
`;

    if (this._loading) {
      this.shadowRoot.innerHTML = `
<style>${SHARED_CSS}${LOCAL_CSS}</style>
<div class="stat is-loading" aria-busy="true" aria-label="Wird geladen…">
  <div class="label">${escHtml(label)}</div>
  <div class="skeleton-line skeleton-value"></div>
  <div class="skeleton-line skeleton-sub"></div>
</div>`;
    } else {
      this.shadowRoot.innerHTML = `
<style>${SHARED_CSS}${LOCAL_CSS}</style>
<div class="stat">
  <div class="label">${escHtml(label)}</div>
  <div class="value ${valclass}">${escHtml(value)}</div>
  <div class="subtitle neu">${escHtml(subtitle)}</div>
</div>`;
    }
  }
}

customElements.define("fd-stat-card", FdStatCard);
