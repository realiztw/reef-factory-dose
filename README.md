# Reef Factory X3 Dosing Pump — Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/realiztw/reef-factory-dose.svg)](https://github.com/realiztw/reef-factory-dose/releases)
[![Validate](https://github.com/realiztw/reef-factory-dose/actions/workflows/validate.yaml/badge.svg)](https://github.com/realiztw/reef-factory-dose/actions/workflows/validate.yaml)

A Home Assistant custom integration for the **Reef Factory X3 Dosing Pump** — a three-channel automated dosing system for reef aquariums (typically used to dose alkalinity, calcium, and magnesium).

This integration connects to the [Smart Reef](https://smartreef.reeffactory.com/) cloud API to surface all three dosing channels' data directly in Home Assistant, enabling automations, dashboards, and long-term dose history tracking.

---

## Features

- **Per-channel container level** — remaining volume in each of the 3 reservoirs (mL)
- **Per-channel container capacity** — total reservoir capacity (mL)
- **Per-channel today dosed** — total volume dosed today per channel (mL)
- **Per-channel daily target** — configured daily dose target per channel (mL, disabled by default)
- **Per-channel automated actions today** — count of automated dosing events today
- Polling every 30 minutes via the Smart Reef WebSocket API
- Full UI-based setup — no YAML configuration required

---

## Prerequisites

- A [Reef Factory X3 Dosing Pump](https://reeffactory.com/product/x3/) device
- A **Smart Reef account** (the same credentials used in the Smart Reef mobile app)
- Your device's **serial number** (found in the Smart Reef app under Device Settings, e.g. `RFDX012345678901`)

---

## Installation

### Via HACS (recommended)

1. Open **HACS** in your Home Assistant instance
2. Go to **Integrations**
3. Click the three-dot menu (⋮) in the top right and choose **Custom repositories**
4. Add the repository URL: `https://github.com/realiztw/reef-factory-dose`
   - Category: **Integration**
5. Click **Add**
6. Find **Reef Factory X3 Dosing Pump** in the HACS integration list and click **Download**
7. Restart Home Assistant

### Manual installation

1. Download the [latest release](https://github.com/realiztw/reef-factory-dose/releases/latest)
2. Copy the `custom_components/reef_factory_dose` folder into your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

---

## Configuration

1. Go to **Settings → Integrations → + Add Integration**
2. Search for **Reef Factory X3 Dosing Pump**
3. Enter your credentials:
   - **Smart Reef Email** — the email address for your Smart Reef account
   - **Smart Reef Password** — your Smart Reef account password
   - **Device Serial Number** — found in the Smart Reef app under your X3's Device Settings (e.g. `RFDX012345678901`)
4. Click **Submit**

The integration will validate your credentials and create all entities automatically.

> **Multiple devices**: You can add the integration multiple times, once per X3 serial number, if you have more than one pump.

---

## Entities

All entities are created under a single device named **X3 Dosing Pump `<serial>`**. Channels are labelled A, B, and C corresponding to the three pump heads.

| Entity | Type | Unit | Channel | Notes |
|--------|------|------|---------|-------|
| Channel A Container Level | Sensor | mL | A | Remaining volume in reservoir |
| Channel B Container Level | Sensor | mL | B | Remaining volume in reservoir |
| Channel C Container Level | Sensor | mL | C | Remaining volume in reservoir |
| Channel A Container Capacity | Sensor | mL | A | Total reservoir capacity (diagnostic, disabled by default) |
| Channel B Container Capacity | Sensor | mL | B | Total reservoir capacity (diagnostic, disabled by default) |
| Channel C Container Capacity | Sensor | mL | C | Total reservoir capacity (diagnostic, disabled by default) |
| Channel A Today Dosed | Sensor | mL | A | Total volume dosed today |
| Channel B Today Dosed | Sensor | mL | B | Total volume dosed today |
| Channel C Today Dosed | Sensor | mL | C | Total volume dosed today |
| Channel A Daily Target | Sensor | mL | A | Configured daily target (diagnostic, disabled by default) |
| Channel B Daily Target | Sensor | mL | B | Configured daily target (diagnostic, disabled by default) |
| Channel C Daily Target | Sensor | mL | C | Configured daily target (diagnostic, disabled by default) |
| Channel A Automated Actions Today | Sensor | actions | A | Count of automated dose events today |
| Channel B Automated Actions Today | Sensor | actions | B | Count of automated dose events today |
| Channel C Automated Actions Today | Sensor | actions | C | Count of automated dose events today |

---

## Automation ideas

```yaml
# Alert when a reservoir is running low (less than 10% remaining)
automation:
  trigger:
    - platform: template
      value_template: >
        {{ (states('sensor.x3_dosing_pump_channel_a_container_level') | float) /
           (states('sensor.x3_dosing_pump_channel_a_container_capacity') | float) < 0.10 }}
  action:
    service: notify.mobile_app
    data:
      message: "X3 Channel A (Alkalinity) is below 10% — top up soon!"

# Track daily dose totals in a logbook
automation:
  trigger:
    platform: time
    at: "23:55:00"
  action:
    service: logbook.log
    data:
      name: X3 Daily Dose Summary
      message: >
        A: {{ states('sensor.x3_dosing_pump_channel_a_today_dosed') }} mL |
        B: {{ states('sensor.x3_dosing_pump_channel_b_today_dosed') }} mL |
        C: {{ states('sensor.x3_dosing_pump_channel_c_today_dosed') }} mL
```

---

## Troubleshooting

**"Invalid email or password"** — Check your Smart Reef app credentials. The email/password used here must be for the Smart Reef account, not the Reef Factory website.

**"Could not connect"** — The integration uses a WebSocket connection to `api.reeffactory.com`. Check that your Home Assistant instance has outbound internet access.

**All channels show the same value** — This was a known issue in early development and has been resolved. If you see this, ensure you are running v1.0.0 or later.

**Entities show `unavailable`** — Check the Home Assistant logs under **Settings → System → Logs** and search for `reef_factory_dose` for more detail.

---

## Contributing

Pull requests and bug reports are welcome! Please open an [issue](https://github.com/realiztw/reef-factory-dose/issues) for any problems or feature requests.

---

## Disclaimer

This integration is not affiliated with or endorsed by Reef Factory. It uses the same WebSocket API as the official Smart Reef web application.

## License

[MIT](LICENSE)
