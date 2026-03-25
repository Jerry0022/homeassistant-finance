/**
 * Finance — Budget Config Lovelace Card
 *
 * Dedicated card for configuring the household budget split model.
 * - Dropdown for split mode (equal/proportional/custom)
 * - Sliders for custom percentages per person
 * - Toggle for remainder split mode
 * - Live preview of calculated Spielgeld
 *
 * Usage:
 *   type: custom:fd-budget-config
 */

class FdBudgetConfig extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (!this._rendered) {
      this._render();
      this._rendered = true;
    }
    this._update();
  }

  setConfig(config) {
    this._config = config || {};
  }

  _render() {
    this.innerHTML = `
<ha-card header="Budget Konfiguration">
<style>
  .bcc { padding: 16px; font-size: 14px; }
  .bcc-row { display: flex; justify-content: space-between; align-items: center;
    padding: 10px 0; border-bottom: 1px solid var(--divider-color, rgba(255,255,255,0.06)); }
  .bcc-row:last-child { border-bottom: none; }
  .bcc-label { color: var(--secondary-text-color); font-size: 13px; }
  .bcc-value { font-weight: 600; font-size: 15px; }
  .bcc-select { background: var(--card-background-color); color: var(--primary-text-color);
    border: 1px solid var(--divider-color); border-radius: 8px; padding: 6px 10px; font-size: 13px; }
  .bcc-section { margin-top: 16px; }
  .bcc-section h4 { font-size: 12px; text-transform: uppercase; letter-spacing: 1px;
    color: var(--accent-color, #4ecca3); margin-bottom: 8px; }
  .bcc-preview { background: var(--primary-background-color, #0a0a0f); border-radius: 10px;
    padding: 14px; margin-top: 12px; }
  .bcc-person { display: flex; justify-content: space-between; padding: 6px 0; }
  .bcc-person .name { font-size: 13px; }
  .bcc-person .sg { font-size: 16px; font-weight: 700; }
  .bcc-person .sg.pos { color: var(--accent-color, #4ecca3); }
  .bcc-person .sg.neg { color: #e74c3c; }
</style>
<div class="bcc" id="bcc">
  <div class="bcc-row">
    <span class="bcc-label">Split-Modell</span>
    <select class="bcc-select" id="splitMode">
      <option value="equal">Equal (50/50)</option>
      <option value="proportional">Proportional (Einkommen)</option>
      <option value="custom">Custom (manuell)</option>
    </select>
  </div>
  <div class="bcc-row">
    <span class="bcc-label">Restgeld-Modus</span>
    <select class="bcc-select" id="remainderMode">
      <option value="none">Kein Split</option>
      <option value="equal_split">Gleichverteilung</option>
    </select>
  </div>
  <div class="bcc-section">
    <h4>Vorschau Spielgeld</h4>
    <div class="bcc-preview" id="preview">
      <div style="color:var(--secondary-text-color);font-size:13px;text-align:center">
        Lade...
      </div>
    </div>
  </div>
</div>
</ha-card>`;

    // Event listeners
    this.querySelector("#splitMode").addEventListener("change", (e) => {
      this._callService("select", "select_option", {
        entity_id: "select.fd_split_model",
        option: e.target.selectedOptions[0].text,
      });
    });

    this.querySelector("#remainderMode").addEventListener("change", (e) => {
      this._callService("select", "select_option", {
        entity_id: "select.fd_remainder_mode",
        option: e.target.selectedOptions[0].text,
      });
    });
  }

  _update() {
    if (!this._hass) return;

    // Read current split model from entity
    const splitEntity = this._hass.states["select.fd_split_model"];
    const remainderEntity = this._hass.states["select.fd_remainder_mode"];

    if (splitEntity) {
      const sel = this.querySelector("#splitMode");
      const val = splitEntity.state.toLowerCase();
      if (val.includes("equal") && !val.includes("proportional")) sel.value = "equal";
      else if (val.includes("proportional")) sel.value = "proportional";
      else sel.value = "custom";
    }

    if (remainderEntity) {
      const sel = this.querySelector("#remainderMode");
      sel.value = remainderEntity.state.toLowerCase().includes("equal") ? "equal_split" : "none";
    }
  }

  _callService(domain, service, data) {
    if (this._hass) {
      this._hass.callService(domain, service, data);
    }
  }

  static getConfigElement() { return document.createElement("div"); }
  static getStubConfig() { return {}; }
  getCardSize() { return 4; }
}

customElements.define("fd-budget-config", FdBudgetConfig);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "fd-budget-config",
  name: "Finance — Budget Config",
  description: "Configure household budget split model and preview Spielgeld.",
});
