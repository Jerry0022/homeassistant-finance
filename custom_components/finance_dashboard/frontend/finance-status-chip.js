/**
 * Finance Status Chip — Lovelace Component
 *
 * Reusable status indicator for the Finance Dashboard.
 * Shows clear visual states: idle, loading, success, error.
 *
 * Usage in Lovelace:
 *   type: custom:finance-status-chip
 *
 * Usage in panels / other components:
 *   <finance-status-chip></finance-status-chip>
 *   element.hass = hass;
 *   element.setState("loading");
 *   element.setState("success");
 *   element.setState("error", "API nicht erreichbar");
 *   element.setState("idle");
 */

const STATES = {
  idle: { icon: "dot", label: null, cls: "idle" },
  loading: { icon: "spinner", label: "Aktualisiert\u2026", cls: "loading" },
  success: { icon: "check", label: "Aktualisiert", cls: "success" },
  error: { icon: "alert", label: "Fehler", cls: "error" },
};

class FinanceStatusChip extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._state = "idle";
    this._lastUpdate = null;
    this._errorMsg = null;
    this._successTimer = null;
    this._rendered = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._rendered) this._render();
  }

  setConfig(config) {
    this._config = config || {};
  }

  connectedCallback() {
    if (!this._rendered) this._render();
  }

  disconnectedCallback() {
    if (this._successTimer) {
      clearTimeout(this._successTimer);
      this._successTimer = null;
    }
  }

  /**
   * Set the chip state. Called by parent components.
   * @param {"idle"|"loading"|"success"|"error"} state
   * @param {string} [errorMsg] - Optional error detail for error state
   */
  setState(state, errorMsg) {
    if (this._successTimer) {
      clearTimeout(this._successTimer);
      this._successTimer = null;
    }

    this._state = state;
    this._errorMsg = state === "error" ? (errorMsg || "Fehler") : null;

    if (state === "success") {
      this._lastUpdate = new Date();
      this._successTimer = setTimeout(() => {
        this._state = "idle";
        this._update();
      }, 2400);
    }

    if (state === "idle" && !this._lastUpdate) {
      this._lastUpdate = new Date();
    }

    this._update();
  }

  /** Update timestamp without changing state */
  setTimestamp(date) {
    this._lastUpdate = date || new Date();
    this._update();
  }

  _render() {
    this._rendered = true;
    this.shadowRoot.innerHTML = `
<style>
:host {
  display: inline-flex;
  --chip-bg: var(--card-background-color, #12121a);
  --chip-bd: rgba(255,255,255,0.06);
  --chip-tx: var(--primary-text-color, #e0e0e0);
  --chip-tx2: var(--secondary-text-color, #9898a8);
  --chip-ac: var(--accent-color, #4ecca3);
  --chip-dg: #e74c3c;
  --chip-wn: #f39c12;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 20px;
  background: var(--chip-bg);
  border: 1px solid var(--chip-bd);
  font-family: 'Segoe UI', system-ui, sans-serif;
  font-size: 12px;
  color: var(--chip-tx2);
  cursor: default;
  user-select: none;
  transition: border-color 0.2s, background 0.2s;
  min-width: 120px;
  height: 32px;
  box-sizing: border-box;
}

/* Clickable in error state */
.chip.error {
  cursor: pointer;
  border-color: rgba(231, 76, 60, 0.3);
  background: rgba(231, 76, 60, 0.06);
}
.chip.error:hover {
  border-color: rgba(231, 76, 60, 0.5);
  background: rgba(231, 76, 60, 0.1);
}

.chip.loading {
  border-color: rgba(78, 204, 163, 0.2);
}

.chip.success {
  border-color: rgba(78, 204, 163, 0.4);
}

/* Icons */
.icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Idle dot */
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--chip-ac);
  opacity: 0.7;
}

/* Spinner — CSS-only ring */
@keyframes chip-spin {
  to { transform: rotate(360deg); }
}
.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(78, 204, 163, 0.2);
  border-top-color: var(--chip-ac);
  border-radius: 50%;
  animation: chip-spin 0.8s linear infinite;
}

/* Checkmark */
.check svg {
  width: 14px;
  height: 14px;
  color: var(--chip-ac);
}

/* Error icon */
.alert svg {
  width: 14px;
  height: 14px;
  color: var(--chip-dg);
}

/* Text */
.label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chip.idle .label { color: var(--chip-tx2); }
.chip.loading .label { color: var(--chip-ac); }
.chip.success .label { color: var(--chip-ac); }
.chip.error .label { color: var(--chip-dg); }

/* Tooltip on error */
.chip[title] { position: relative; }
</style>

<div class="chip idle" id="chip">
  <div class="icon" id="icon"></div>
  <span class="label" id="label"></span>
</div>`;

    this.shadowRoot.getElementById("chip")
      .addEventListener("click", () => this._onClick());
    this._update();
  }

  _update() {
    if (!this._rendered) return;
    const chip = this.shadowRoot.getElementById("chip");
    const icon = this.shadowRoot.getElementById("icon");
    const label = this.shadowRoot.getElementById("label");
    if (!chip) return;

    const s = STATES[this._state] || STATES.idle;

    // Update class
    chip.className = `chip ${s.cls}`;

    // Update icon
    icon.innerHTML = this._renderIcon(s.icon);

    // Update label
    const text = this._getLabelText(s);
    label.textContent = text;

    // Tooltip for error
    if (this._state === "error" && this._errorMsg) {
      chip.title = `${this._errorMsg} — Klicken zum Wiederholen`;
    } else {
      chip.removeAttribute("title");
    }
  }

  _renderIcon(type) {
    switch (type) {
      case "dot":
        return '<div class="dot"></div>';
      case "spinner":
        return '<div class="spinner"></div>';
      case "check":
        return '<div class="check"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg></div>';
      case "alert":
        return '<div class="alert"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg></div>';
      default:
        return "";
    }
  }

  _getLabelText(s) {
    if (this._state === "error") {
      return this._errorMsg || "Fehler";
    }
    if (s.label) return s.label;
    // idle — show timestamp
    if (this._lastUpdate) {
      const hh = String(this._lastUpdate.getHours()).padStart(2, "0");
      const mm = String(this._lastUpdate.getMinutes()).padStart(2, "0");
      return `Stand ${hh}:${mm}`;
    }
    return "Bereit";
  }

  _onClick() {
    if (this._state === "error") {
      this.dispatchEvent(new CustomEvent("retry", { bubbles: true, composed: true }));
    }
  }

  // --- Lovelace card interface ---
  static getConfigElement() {
    return document.createElement("finance-status-chip-editor");
  }

  static getStubConfig() {
    return {};
  }

  getCardSize() {
    return 1;
  }
}

// Minimal editor for Lovelace card picker
class FinanceStatusChipEditor extends HTMLElement {
  setConfig(config) {
    this._config = Object.assign({}, config);
    if (!this.innerHTML) {
      this.innerHTML = `<div style="padding:16px;color:var(--secondary-text-color);font-size:13px;">
        Status Chip zeigt automatisch den Aktualisierungsstatus des Finance Dashboard.
      </div>`;
    }
  }

  _dispatch() {
    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config: this._config }, bubbles: true, composed: true,
    }));
  }
}

customElements.define("finance-status-chip", FinanceStatusChip);
customElements.define("finance-status-chip-editor", FinanceStatusChipEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "finance-status-chip",
  name: "Finance Status Chip",
  description: "Zeigt den Aktualisierungsstatus des Finance Dashboard",
  preview: true,
});
