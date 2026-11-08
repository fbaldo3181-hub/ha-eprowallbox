/**
 * eProWallbox Card
 *
 * Lovelace card showing the state of an eProWallbox charger and letting you
 * start / stop charging.
 *
 * Minimal configuration (the eProWallbox device is auto-detected):
 *
 *   type: custom:eprowallbox-card
 *
 * Full configuration:
 *
 *   type: custom:eprowallbox-card
 *   header: eProWallbox
 *   device_id: <device id>        # optional if only one eProWallbox
 *   show_phases: true             # per-phase voltage / current / power
 *   show_details: true            # charge time, temperature, limits...
 *                                 # a current limit slider is shown when
 *                                 # the number entity exists
 *   entities:                     # optional manual overrides (key: entity_id)
 *     charging_enabled: switch.my_custom_switch
 */

const LitElement = customElements.get("hui-masonry-view")
  ? Object.getPrototypeOf(customElements.get("hui-masonry-view"))
  : Object.getPrototypeOf(customElements.get("hui-view"));
const html = LitElement.prototype.html;
const css = LitElement.prototype.css;

const CARD_VERSION = "0.3.0";

console.info(
  `%c EPROWALLBOX-CARD %c v${CARD_VERSION} `,
  "color: orange; font-weight: bold; background: black",
  "color: white; font-weight: bold; background: dimgray"
);

const PLATFORM = "eprowallbox";
const PHASES = ["l1", "l2", "l3"];

// Entity keys of the integration, per domain. The card finds each entity of
// the device by the end of its entity_id (longest key wins).
const PHASE_KEYS = [
  "voltage",
  "thd_voltage",
  "current",
  "thd_current",
  "active_power",
  "reactive_power",
  "apparent_power",
  "active_energy",
  "reactive_energy",
].flatMap((prefix) => PHASES.map((p) => `${prefix}_${p}`));

const ENTITY_KEYS = {
  sensor: [
    "serial_number",
    "firmware_version",
    "modbus_map_version",
    "device_type",
    "hw_current_limit",
    "actual_error",
    "general_status",
    "ocpp_status",
    "user_current_limit",
    "current_limit",
    "fallback_current",
    "load_unbalance_current",
    "watchdog_timer",
    "meter_used",
    "charge_time",
    "temperature",
    ...PHASE_KEYS,
  ],
  binary_sensor: [
    "status",
    "load_unbalance_limiting",
    "dpm_limiting",
    "temperature_derating",
    "dpm_enabled",
    "mid_meter_enabled",
    "load_unbalance_enabled",
    "watchdog_enabled",
  ],
  switch: ["charging_enabled"],
  number: ["current_limit_setpoint"],
};

// IEC 61851 states (register 40101: 0 = A1 ... 9 = F)
const GENERAL_STATUS = [
  { label: "No vehicle (A1)", icon: "mdi:power-plug-off", color: "var(--secondary-text-color)" },
  { label: "No vehicle (A2)", icon: "mdi:power-plug-off", color: "var(--secondary-text-color)" },
  { label: "Vehicle connected (B1)", icon: "mdi:car-electric", color: "var(--info-color, var(--primary-color))" },
  { label: "Vehicle connected (B2)", icon: "mdi:car-electric", color: "var(--info-color, var(--primary-color))" },
  { label: "Charging (C1)", icon: "mdi:ev-station", color: "var(--success-color, green)" },
  { label: "Charging (C2)", icon: "mdi:ev-station", color: "var(--success-color, green)" },
  { label: "Charging, ventilation (D1)", icon: "mdi:ev-station", color: "var(--success-color, green)" },
  { label: "Charging, ventilation (D2)", icon: "mdi:ev-station", color: "var(--success-color, green)" },
  { label: "Error (E)", icon: "mdi:alert-circle", color: "var(--error-color, red)" },
  { label: "Fault (F)", icon: "mdi:alert-circle", color: "var(--error-color, red)" },
];

// OCPP connector status (register 40102: 0 = Available ... 8 = Faulted)
const OCPP_STATUS = [
  "Available",
  "Preparing",
  "Charging",
  "Suspended by EVSE",
  "Suspended by EV",
  "Finishing",
  "Reserved",
  "Unavailable",
  "Faulted",
];

const UNAVAILABLE = ["unavailable", "unknown"];

class EprowallboxCard extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      config: { type: Object },
      _busy: { state: true },
      _limitDraft: { state: true },
    };
  }

  static getConfigElement() {
    return document.createElement("eprowallbox-card-editor");
  }

  static getStubConfig() {
    return {
      header: "eProWallbox",
      show_phases: true,
      show_details: true,
    };
  }

  setConfig(config) {
    if (!config) {
      throw new Error("Invalid configuration");
    }
    this.config = {
      header: "eProWallbox",
      show_phases: true,
      show_details: true,
      ...config,
    };
    this._resolved = null;
  }

  getCardSize() {
    return 6;
  }

  getGridOptions() {
    return {
      rows: 6,
      columns: 12,
      min_rows: 3,
      min_columns: 6,
    };
  }

  // ---------------------------------------------------------------------
  // Entity resolution
  // ---------------------------------------------------------------------

  /** Map each integration key to the entity_id of the selected device. */
  _resolve() {
    const hass = this.hass;
    if (!hass || !hass.entities) return {};
    if (this._resolved && this._resolvedFor === hass.entities) {
      return this._resolved;
    }

    const all = Object.values(hass.entities);
    let deviceId = this.config.device_id;
    if (!deviceId) {
      const own = all.find((e) => e.platform === PLATFORM && e.device_id);
      deviceId = own ? own.device_id : null;
    }

    const map = {};
    if (deviceId) {
      for (const ent of all) {
        if (ent.device_id !== deviceId) continue;
        const [domain, objectId] = ent.entity_id.split(".");
        const keys = ENTITY_KEYS[domain];
        if (!keys) continue;
        let best = null;
        for (const key of keys) {
          if (
            (objectId === key || objectId.endsWith(`_${key}`)) &&
            (!best || key.length > best.length)
          ) {
            best = key;
          }
        }
        if (best) map[best] = ent.entity_id;
      }
    }

    Object.assign(map, this.config.entities || {});
    this._resolved = map;
    this._resolvedFor = hass.entities;
    return map;
  }

  _stateObj(key) {
    const entityId = this._resolve()[key];
    return entityId ? this.hass.states[entityId] : undefined;
  }

  _num(key) {
    const stateObj = this._stateObj(key);
    if (!stateObj || UNAVAILABLE.includes(stateObj.state)) return null;
    const value = parseFloat(stateObj.state);
    return Number.isNaN(value) ? null : value;
  }

  _isOn(key) {
    const stateObj = this._stateObj(key);
    return !!stateObj && stateObj.state === "on";
  }

  // ---------------------------------------------------------------------
  // Formatting
  // ---------------------------------------------------------------------

  _fmt(value, digits = 0, unit = "") {
    if (value === null || value === undefined) return "–";
    return `${value.toFixed(digits)}${unit ? ` ${unit}` : ""}`;
  }

  _fmtPower(watts) {
    if (watts === null) return "–";
    return Math.abs(watts) >= 1000
      ? `${(watts / 1000).toFixed(2)} kW`
      : `${Math.round(watts)} W`;
  }

  _fmtDuration(seconds) {
    if (seconds === null) return "–";
    const s = Math.round(seconds);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const r = s % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(h)}:${pad(m)}:${pad(r)}`;
  }

  _sum(prefix) {
    const values = PHASES.map((p) => this._num(`${prefix}_${p}`));
    if (values.every((v) => v === null)) return null;
    return values.reduce((acc, v) => acc + (v ?? 0), 0);
  }

  // ---------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------

  _moreInfo(key) {
    const entityId = this._resolve()[key];
    if (!entityId) return;
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId },
        bubbles: true,
        composed: true,
      })
    );
  }

  async _toggleCharging() {
    const entityId = this._resolve().charging_enabled;
    if (!entityId || this._busy) return;
    const service = this._isOn("charging_enabled") ? "turn_off" : "turn_on";
    this._busy = true;
    try {
      await this.hass.callService("switch", service, { entity_id: entityId });
    } finally {
      // The state is read back from the wallbox; leave it a moment to update.
      setTimeout(() => {
        this._busy = false;
      }, 1500);
    }
  }

  _limitInput(ev) {
    this._limitDraft = Number(ev.target.value);
  }

  async _setLimit(ev) {
    const entityId = this._resolve().current_limit_setpoint;
    if (!entityId) return;
    const value = Number(ev.target.value);
    this._limitDraft = value;
    try {
      await this.hass.callService("number", "set_value", {
        entity_id: entityId,
        value,
      });
    } finally {
      // The value is read back from the wallbox; leave it a moment to update.
      setTimeout(() => {
        this._limitDraft = null;
      }, 1500);
    }
  }

  // ---------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------

  render() {
    if (!this.hass || !this.config) {
      return html`
        <ha-card>
          <div class="card-content loading">
            <ha-spinner size="small"></ha-spinner>
          </div>
        </ha-card>
      `;
    }

    const resolved = this._resolve();
    if (!resolved.general_status && !resolved.charging_enabled) {
      return html`
        <ha-card header="${this.config.header || ""}">
          <div class="card-content">
            <ha-alert alert-type="warning">
              No eProWallbox entities found. Select the device in the card
              editor (device_id), or check that the integration is set up.
            </ha-alert>
          </div>
        </ha-card>
      `;
    }

    return html`
      <ha-card header="${this.config.header || ""}">
        <div class="card-content">
          ${this._renderStatus()} ${this._renderChips()}
          ${this._renderControl()} ${this._renderLimit()}
          ${this.config.show_phases ? this._renderPhases() : ""}
          ${this.config.show_details ? this._renderDetails() : ""}
        </div>
      </ha-card>
    `;
  }

  _renderStatus() {
    const statusObj = this._stateObj("general_status");
    const available = statusObj && !UNAVAILABLE.includes(statusObj.state);
    const code = this._num("general_status");
    const info =
      available && code !== null
        ? GENERAL_STATUS[code] || {
            label: `Status ${code}`,
            icon: "mdi:help-circle",
            color: "var(--secondary-text-color)",
          }
        : {
            label: "Unavailable",
            icon: "mdi:lan-disconnect",
            color: "var(--disabled-text-color)",
          };

    const ocppCode = this._num("ocpp_status");
    const ocpp = ocppCode !== null ? OCPP_STATUS[ocppCode] : null;
    const power = this._sum("active_power");

    return html`
      <div class="status" @click=${() => this._moreInfo("general_status")}>
        <ha-icon
          class="status-icon"
          .icon=${info.icon}
          style="color: ${info.color}"
        ></ha-icon>
        <div class="status-text">
          <div class="status-label">${info.label}</div>
          ${ocpp ? html`<div class="status-sub">OCPP: ${ocpp}</div>` : ""}
        </div>
        <div class="status-power">${this._fmtPower(power)}</div>
      </div>
    `;
  }

  _renderChips() {
    const chips = [];
    const error = this._num("actual_error");
    if (error !== null && error !== 0) {
      chips.push({ icon: "mdi:alert-circle", text: `Error ${error}`, type: "error" });
    }
    if (this._isOn("temperature_derating")) {
      chips.push({ icon: "mdi:thermometer-alert", text: "Temperature derating", type: "warning" });
    }
    if (this._isOn("dpm_limiting")) {
      chips.push({ icon: "mdi:speedometer-slow", text: "DPM limiting", type: "warning" });
    }
    if (this._isOn("load_unbalance_limiting")) {
      chips.push({ icon: "mdi:scale-unbalanced", text: "Load unbalance limiting", type: "warning" });
    }
    if (!chips.length) return "";
    return html`
      <div class="chips">
        ${chips.map(
          (chip) => html`
            <span class="chip ${chip.type}">
              <ha-icon .icon=${chip.icon}></ha-icon>${chip.text}
            </span>
          `
        )}
      </div>
    `;
  }

  _renderControl() {
    const switchObj = this._stateObj("charging_enabled");
    if (!switchObj) {
      return html`<div class="empty">Charging switch not found</div>`;
    }
    const unavailable = UNAVAILABLE.includes(switchObj.state);
    const on = switchObj.state === "on";
    return html`
      <div class="control">
        <button
          class="action ${on ? "stop" : "start"}"
          ?disabled=${unavailable || this._busy}
          @click=${this._toggleCharging}
        >
          <ha-icon .icon=${on ? "mdi:stop" : "mdi:play"}></ha-icon>
          ${on ? "Stop charging" : "Start charging"}
        </button>
        <div class="control-hint">
          ${unavailable
            ? "Switch unavailable"
            : on
              ? "Charging is enabled"
              : "Charging is disabled"}
        </div>
      </div>
    `;
  }

  _renderLimit() {
    const numberObj = this._stateObj("current_limit_setpoint");
    if (!numberObj) return "";
    const unavailable = UNAVAILABLE.includes(numberObj.state);
    const attrs = numberObj.attributes;
    const min = attrs.min ?? 6;
    const max = attrs.max ?? 32;
    const step = attrs.step ?? 1;
    const current = unavailable ? min : parseFloat(numberObj.state);
    const value = this._limitDraft ?? current;
    return html`
      <div class="limit">
        <div class="limit-header">
          <span class="label">Current limit setpoint</span>
          <span class="value">${unavailable ? "–" : `${value} A`}</span>
        </div>
        <input
          type="range"
          min=${min}
          max=${max}
          step=${step}
          .value=${String(value)}
          ?disabled=${unavailable}
          @input=${this._limitInput}
          @change=${this._setLimit}
        />
      </div>
    `;
  }

  _renderPhases() {
    return html`
      <table class="phases">
        <thead>
          <tr>
            <th></th>
            <th>Voltage</th>
            <th>Current</th>
            <th>Power</th>
          </tr>
        </thead>
        <tbody>
          ${PHASES.map(
            (p) => html`
              <tr>
                <td class="phase">${p.toUpperCase()}</td>
                <td>${this._fmt(this._num(`voltage_${p}`), 1, "V")}</td>
                <td>${this._fmt(this._num(`current_${p}`), 2, "A")}</td>
                <td>${this._fmtPower(this._num(`active_power_${p}`))}</td>
              </tr>
            `
          )}
        </tbody>
      </table>
    `;
  }

  _renderDetails() {
    const energyWh = this._sum("active_energy");
    const rows = [
      ["Charge time", this._fmtDuration(this._num("charge_time")), "charge_time"],
      ["Energy counter", energyWh === null ? "–" : `${(energyWh / 1000).toFixed(2)} kWh`, "active_energy_l1"],
      ["Current limit", this._fmt(this._num("current_limit"), 0, "A"), "current_limit"],
      ["User limit", this._fmt(this._num("user_current_limit"), 0, "A"), "user_current_limit"],
      ["Temperature", this._fmt(this._num("temperature"), 1, "°C"), "temperature"],
    ];
    return html`
      <div class="details">
        ${rows.map(
          ([label, value, key]) => html`
            <div class="row" @click=${() => this._moreInfo(key)}>
              <span class="label">${label}</span>
              <span class="value">${value}</span>
            </div>
          `
        )}
      </div>
    `;
  }

  static get styles() {
    return css`
      :host {
        display: block;
      }
      .card-content {
        padding: 0 16px 16px;
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      .loading {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 32px 16px;
      }
      .status {
        display: flex;
        align-items: center;
        gap: 12px;
        cursor: pointer;
      }
      .status-icon {
        --mdc-icon-size: 40px;
      }
      .status-text {
        flex: 1;
        min-width: 0;
      }
      .status-label {
        font-size: 1.1em;
        font-weight: 500;
        color: var(--primary-text-color);
      }
      .status-sub {
        font-size: 0.85em;
        color: var(--secondary-text-color);
      }
      .status-power {
        font-size: 1.6em;
        font-weight: bold;
        color: var(--primary-text-color);
        white-space: nowrap;
      }
      .chips {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
      }
      .chip {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 2px 10px 2px 6px;
        border-radius: 12px;
        font-size: 0.85em;
        color: var(--primary-text-color);
        --mdc-icon-size: 16px;
      }
      .chip.warning {
        background: color-mix(in srgb, var(--warning-color, orange) 25%, transparent);
      }
      .chip.error {
        background: color-mix(in srgb, var(--error-color, red) 25%, transparent);
      }
      .control {
        display: flex;
        flex-direction: column;
        align-items: stretch;
        gap: 4px;
      }
      .action {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        padding: 12px 16px;
        border: none;
        border-radius: 12px;
        font-size: 1em;
        font-weight: 500;
        font-family: inherit;
        color: var(--text-primary-color, white);
        cursor: pointer;
      }
      .action.start {
        background: var(--success-color, green);
      }
      .action.stop {
        background: var(--error-color, red);
      }
      .action:disabled {
        opacity: 0.5;
        cursor: default;
      }
      .control-hint {
        text-align: center;
        font-size: 0.85em;
        color: var(--secondary-text-color);
      }
      .limit {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
      .limit-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .limit input[type="range"] {
        width: 100%;
        accent-color: var(--primary-color);
      }
      .phases {
        width: 100%;
        border-collapse: collapse;
        text-align: right;
        color: var(--primary-text-color);
      }
      .phases th {
        font-weight: 500;
        font-size: 0.85em;
        color: var(--secondary-text-color);
        padding: 4px 0;
      }
      .phases td {
        padding: 4px 0;
      }
      .phases .phase {
        text-align: left;
        font-weight: 500;
      }
      .details {
        border-top: 1px solid var(--divider-color);
        padding-top: 8px;
      }
      .row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 4px 0;
        cursor: pointer;
      }
      .label {
        color: var(--secondary-text-color);
      }
      .value {
        font-weight: 500;
        color: var(--primary-text-color);
      }
      .empty {
        color: var(--secondary-text-color);
        font-style: italic;
        text-align: center;
        padding: 8px;
      }
    `;
  }
}

/**
 * Card Editor
 */
const EDITOR_SCHEMA = [
  { name: "header", selector: { text: {} } },
  { name: "device_id", selector: { device: { integration: PLATFORM } } },
  { name: "show_phases", selector: { boolean: {} } },
  { name: "show_details", selector: { boolean: {} } },
];

const EDITOR_LABELS = {
  header: "Header",
  device_id: "Device (optional, auto-detected)",
  show_phases: "Show per-phase measurements",
  show_details: "Show details (charge time, limits, temperature)",
};

class EprowallboxCardEditor extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      config: { type: Object },
    };
  }

  setConfig(config) {
    this.config = config;
  }

  render() {
    if (!this.hass || !this.config) {
      return html``;
    }

    return html`
      <ha-form
        .hass=${this.hass}
        .data=${this.config}
        .schema=${EDITOR_SCHEMA}
        .computeLabel=${(schema) => EDITOR_LABELS[schema.name] || schema.name}
        @value-changed=${this._valueChanged}
      ></ha-form>
    `;
  }

  _valueChanged(ev) {
    const config = { ...ev.detail.value };
    if (!config.device_id) {
      delete config.device_id;
    }
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config },
        bubbles: true,
        composed: true,
      })
    );
  }
}

if (!customElements.get("eprowallbox-card")) {
  customElements.define("eprowallbox-card", EprowallboxCard);
}
if (!customElements.get("eprowallbox-card-editor")) {
  customElements.define("eprowallbox-card-editor", EprowallboxCardEditor);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "eprowallbox-card",
  name: "eProWallbox Card",
  description: "Status and charging control for eProWallbox chargers",
  preview: true,
});
