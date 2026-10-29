/**
 * fd-subpage-header — the one header every subpage shares.
 *
 *   [← back, 44 px] [Title, ellipsized] [optional actions]
 *
 * Usage:
 *   <fd-subpage-header title="Verträge">
 *     <button slot="actions">…</button>      (optional, trailing)
 *   </fd-subpage-header>
 *
 * Properties / attributes:
 *   title   (attribute or property) heading text. The native `title` attribute is
 *           stripped after it is read, so the browser's own tooltip never shows;
 *           a truncated heading gets the app-styled tooltip instead.
 *   back-label (attribute, optional) accessible label of the back button.
 *
 * Events (bubbling, composed):
 *   fd-navigate {target:"back"}   back button, or Esc anywhere on the page
 *                                  (not while typing in a field, not when another
 *                                  handler already consumed the key)
 *
 * Layout: never overflows. The title shrinks and ellipsizes (full text on
 * hover/focus), actions keep their size, the bar wraps nothing.
 * Contract: docs/dev/ui-concept-gap.md § 1.2 / § 1.7, decision 2.
 */

/*FB-START*/
const FB = {
  de: { "sph.back": "Zurück" },
  en: { "sph.back": "Back" },
};
/*FB-END*/

function tr(key) {
  let s = window._fd.tSync(key);
  if (s !== key) return s;
  const raw = ((window._fd._hass && window._fd._hass.language) || navigator.language || "en").toLowerCase();
  return (FB[raw.startsWith("de") ? "de" : "en"][key]) || key;
}

const CSS = `
:host { display: block; position: sticky; top: 0; z-index: 5; background: var(--fd-page); }
.bar { display: flex; align-items: center; gap: 4px; min-height: var(--fd-touch); padding: 4px 0; box-sizing: border-box; max-width: 100%; }
button { font: inherit; color: inherit; cursor: pointer; }
.back { flex: none; display: inline-flex; align-items: center; justify-content: center; width: var(--fd-touch); height: var(--fd-touch); margin-left: -8px; padding: 0; border: 0; border-radius: var(--fd-r-pill); background: transparent; color: var(--fd-t1); }
.back:hover { background: var(--fd-sunk); }
.back svg { width: 22px; height: 22px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.ttl { position: relative; flex: 1 1 0; min-width: 0; }
.ttl h1 { margin: 0; font-size: 18px; font-weight: 500; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ttl[data-tip]::after { left: 0; transform: none; }
.act { flex: none; display: flex; align-items: center; gap: 4px; max-width: 60%; }
`;

class FdSubpageHeader extends HTMLElement {
  static get observedAttributes() { return ["title", "back-label"]; }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._title = "";
    this._ro = null;
    this._onKey = (e) => this._key(e);
  }

  get title() { return this._title; }
  set title(v) { this._title = v == null ? "" : String(v); this._render(); }

  attributeChangedCallback(name, _old, val) {
    if (name === "title") {
      if (val == null) return; // our own removeAttribute below
      this._title = String(val);
      this.removeAttribute("title"); // no native tooltip, ever
    }
    this._render();
  }

  connectedCallback() {
    this._render();
    document.addEventListener("keydown", this._onKey);
    if (typeof ResizeObserver === "function") {
      this._ro = new ResizeObserver(() => this._fit());
      this._ro.observe(this);
    }
    // Locale files load async; re-label once they are there.
    window._fd.t("sph.back").then(() => this.isConnected && this._render());
  }

  disconnectedCallback() {
    document.removeEventListener("keydown", this._onKey);
    if (this._ro) { this._ro.disconnect(); this._ro = null; }
  }

  _key(e) {
    if (e.key !== "Escape" || e.defaultPrevented || !this.isConnected) return;
    if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
    const el = e.composedPath()[0];
    if (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return;
    e.preventDefault();
    this._back();
  }

  _back() {
    this.dispatchEvent(new CustomEvent("fd-navigate", { bubbles: true, composed: true, detail: { target: "back" } }));
  }

  /** Tooltip + focus stop only when the title is actually cut off. */
  _fit() {
    const wrap = this.shadowRoot.querySelector(".ttl");
    const h = wrap && wrap.firstElementChild;
    if (!wrap || !h) return;
    if (h.scrollWidth > h.clientWidth + 1) {
      wrap.setAttribute("data-tip", this._title);
      wrap.setAttribute("tabindex", "0");
    } else {
      wrap.removeAttribute("data-tip");
      wrap.removeAttribute("tabindex");
    }
  }

  _render() {
    if (!this.shadowRoot) return;
    const { SHARED_CSS, escHtml } = window._fd;
    const label = this.getAttribute("back-label") || tr("sph.back");
    this.shadowRoot.innerHTML = `<style>${SHARED_CSS}${CSS}</style>
<div class="bar">
  <button class="back" type="button" aria-label="${escHtml(label)}" data-tip="${escHtml(label)} (Esc)">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>
  </button>
  <div class="ttl"><h1>${escHtml(this._title)}</h1></div>
  <div class="act"><slot name="actions"></slot><slot></slot></div>
</div>`;
    this.shadowRoot.querySelector(".back").addEventListener("click", () => this._back());
    this._fit();
    requestAnimationFrame(() => this._fit());
  }
}

window._fd.defineOnce("fd-subpage-header", FdSubpageHeader);
