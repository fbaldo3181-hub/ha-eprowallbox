# eProWallbox

A Home Assistant integration for eProWallbox chargers, using the wallbox's **Modbus TCP** interface.

[![HACS Default](https://img.shields.io/badge/HACS-Default-blue.svg)](https://github.com/hacs/integration)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2025.7%2B-blue.svg)](https://www.home-assistant.io/)

> This integration and the author are not affiliate to eSolutions-charging nor free2move. eSolutions-charging and free2move are registered trademarks.

> ⚠️ This integration has been tested with eProWallbox Move only. It should work with other models using Modbus implementation but the entitie may be at different addresses.

## Features

- Local polling over Modbus TCP, no cloud and no account required
- Per-phase (L1 / L2 / L3) voltage, current, power, energy and THD measurements
- Charging status, OCPP status, error code, charge time and temperature
- Current limits (hardware, user, EMS setpoint, fallback)
- Binary sensors for limiting / derating states and enabled features
- A switch to enable or disable charging
- A number to set the charging current limit (EMS setpoint)
- A Lovelace card showing the charger state with start / stop and current limit controls
- Each value is refreshed at its own interval, so the wallbox is not flooded with requests

## Requirements

- Modbus TCP enabled on the wallbox and reachable from Home Assistant (default port `502`, unit ID `1`)
- A fixed IP address (or DHCP reservation) for the wallbox is recommended

## Installation via HACS

1. Open HACS in Home Assistant
2. Go to Integrations
3. Search for "eProWallbox"
4. Install and restart Home Assistant

## Manual Installation

1. Copy `custom_components/eprowallbox/` into your HA `config/custom_components/`
2. Restart Home Assistant
3. Add the integration via Settings > Devices & Services > Add Integration

## Configuration

Add the integration via Settings > Devices & Services > Add Integration > eProWallbox, then enter:

| Field | Description | Default |
| ----- | ----------- | ------- |
| Host | IP address or hostname of the wallbox | – |
| Port | Modbus TCP port | `502` |

The connection is tested when you validate the form (the wallbox serial number register is read). Host and port can be changed later from the integration's options.

## Entities

### Sensors

| Group | Entities | Refresh |
| ----- | -------- | ------- |
| Status | General Status (IEC 61851), OCPP Status, Actual Error | 5–10 s |
| Session | Charge Time, Temperature (°C) | 30 s |
| Voltage | Voltage L1 / L2 / L3 (V) | 10 s |
| Current | Current L1 / L2 / L3 (A) | 10 s |
| Active power | Active Power L1 / L2 / L3 (W) | 10 s |
| Reactive / apparent power | Reactive Power (var), Apparent Power (VA) per phase | 30 s |
| Energy | Active Energy (Wh), Reactive Energy (varh) per phase | 30–60 s |
| Current limits | Current Limit (EMS setpoint), User Current Limit | 15–30 s |
| Diagnostic | Serial Number, Firmware Version, Modbus Map Version, Device Type, HW Current Limit, Fallback Current, Load Unbalance Current, Watchdog Timer, Meter Used, THD Voltage / THD Current per phase | 1 min–1 h |

Diagnostic entities are hidden from the default dashboard but remain available in the device page.

### Binary sensors

| Entity | Meaning |
| ------ | ------- |
| Status | Wallbox reachable (connectivity) |
| Load Unbalance Limiting | Charging current is limited by load unbalance |
| DPM Limiting | Charging current is limited by dynamic power management |
| Temperature Derating | Charging is derated because of temperature (problem) |
| DPM Enabled, MID Meter Enabled, Load Unbalance Enabled, Watchdog Enabled | Feature enabled on the wallbox (diagnostic) |

### Switch

| Entity | Description |
| ------ | ----------- |
| Charging Enabled | Enables (`1`) or disables (`0`) charging. The state is read back from the wallbox after each command. |

### Number

| Entity | Description |
| ------ | ----------- |
| Current Limit Setpoint | Charging current limit in amperes (EMS setpoint, register 40407). The range goes from 6 A to the hardware limit set with the rotary selector. The value is read back from the wallbox after each change. |

If the watchdog is enabled on the wallbox, the setpoint may fall back to the *Fallback Current* when it is not refreshed regularly. Check the *Watchdog Enabled* binary sensor and the *Watchdog Timer* sensor.

## Card

The card shows the charger status, power, per-phase measurements and details, with a button to start / stop charging and a slider for the current limit setpoint.

```yaml
type: custom:eprowallbox-card
header: eProWallbox
device_id: <device id>        # optional if only one eProWallbox
show_phases: true             # per-phase voltage / current / power
show_details: true            # charge time, temperature, limits...
```

The eProWallbox device is detected automatically. Options:

| Option | Description | Default |
| ------ | ----------- | ------- |
| `header` | Card title | `eProWallbox` |
| `device_id` | Device to display (needed only with several chargers) | auto |
| `show_phases` | Show per-phase voltage / current / power | `true` |
| `show_details` | Show charge time, energy counter, limits and temperature | `true` |
| `entities` | Manual overrides, e.g. `charging_enabled: switch.my_switch` | – |

## Troubleshooting

- **Cannot connect**: check the IP address and port, and make sure Modbus TCP is enabled on the wallbox. Only one Modbus TCP client may be allowed at a time, so close any other tool (or a previous `modbus:` block in `configuration.yaml`) that talks to the wallbox.
- **Missing values after startup**: slow-changing values (serial number, firmware, settings) are read at long intervals and appear after the first refresh.
- Enable debug logs for `custom_components.eprowallbox` to see register read errors.

## Links

- [Documentation](https://github.com/fbaldo3181-hub/ha-eprowallbox)
- [Issues](https://github.com/fbaldo3181-hub/ha-eprowallbox/issues)

## License

MIT