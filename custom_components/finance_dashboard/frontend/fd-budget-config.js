/**
 * Finance — Budget Config Lovelace Card
 *
 * Two dropdowns for the household split model and the remainder mode. Both
 * drive the integration's own select entities, so the option list and the
 * current value come from the entity (the source of truth), never from
 * labels hard-coded here, and the card keeps working when the sensor
 * platform is down. Budgets themselves live in the panel (Einstellungen).
 *
 * Usage:
 *   type: custom:fd-budget-config
 *   split_entity: select.fd_split_model        # optional, this is the default
 *   remainder_entity: select.fd_remainder_mode # optional, this is the default
 */

const ROWS = [
  { key: "split_entity", fallback: "select.fd_split_model", label: "Split-Modell" },
  { key: "remainder_entity", fallback: "select.fd_remainder_mode", label: "Restgeld-Modus" },
];

class FdBudgetConfig extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._sig = null;
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _entityIds() {
    const c = this._config || {};
    return ROWS.map((r) => c[r.key] || r.fallback);
  }

  _render() {
    if (!this._hass) return;
    const { escHtml } = window._fd;
    const ids = this._entityIds();
    const states = ids.map((id) => this._hass.states[id]);
    // Re-render only when the entities actually changed — hass is set on
    // every state change in the whole instance.
    const sig = JSON.stringify(states.map((s) => s && [s.state, s.attributes.options]));
    if (sig === this._sig) return;
    this._sig = sig;

    const rows = ROWS.map((r, i) => {
      const st = states[i];
      if (!st) {
        return `<div class="bcc-row"><span class="bcc-label">${escHtml(r.label)}</span>
          <span class="bcc-missing">${escHtml(ids[i])} fehlt</span></div>`;
      }
      const opts = (st.attributes.options || []).map((o) =>
        `<option value="${escHtml(o)}"${o === st.state ? " selected" : ""}>${escHtml(o)}</option>`).join("");
      return `<div class="bcc-row"><label class="bcc-label" for="s${i}">${escHtml(r.label)}</label>
        <select class="bcc-select" id="s${i}" data-entity="${escHtml(ids[i])}">${opts}</select></div>`;
    }).join("");

    this.innerHTML = `
<ha-card header="Budget-Aufteilung">
<style>
  .bcc { padding: 0 16px 12px; font-size: 14px; }
  .bcc-row { display: flex; justify-content: space-between; align-items: center; gap: 12px;
    padding: 10px 0; border-bottom: 1px solid var(--divider-color); }
  .bcc-row:last-child { border-bottom: none; }
  .bcc-label { color: var(--secondary-text-color); font-size: 13px; flex: 0 0 auto; }
  .bcc-select { min-width: 0; max-width: 60%; background: var(--card-background-color);
    color: var(--primary-text-color); border: 1px solid var(--divider-color);
    border-radius: 8px; padding: 6px 10px; font-size: 13px; }
  .bcc-missing { color: var(--warning-color); font-size: 12px; overflow-wrap: anywhere; }
</style>
<div class="bcc">${rows}</div>
</ha-card>`;

    this.querySelectorAll("select[data-entity]").forEach((sel) => {
      sel.addEventListener("change", () => {
        this._hass.callService("select", "select_option", {
          entity_id: sel.dataset.entity,
          option: sel.value,
        });
      });
    });
  }

  static getConfigElement() { return document.createElement("div"); }
  static getStubConfig() { return {}; }
  getCardSize() { return 2; }

  // Sections view: width in columns (multiple of 3 of the 12-col grid), height in rows.
  getGridOptions() {
    return { columns: 6, min_columns: 6, rows: 2, min_rows: 2, max_rows: 4 };
  }
}

window._fd.defineOnce("fd-budget-config", FdBudgetConfig);

window._fd.registerCard({
  type: "fd-budget-config",
  name: "Finance — Budget Config",
  description: "Split model and remainder mode of the household budget.",
});
