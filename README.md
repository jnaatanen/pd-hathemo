# PapaDog's Home Assistant Themo Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A [Home Assistant](https://www.home-assistant.io/) custom integration for
[Themo](https://themo.io) smart thermostats, built directly on the Themo Public API v2.1.

It draws inspiration from the `pythemo` library / `homeassistant-pythemo` integration by
Jonne Datanen.

## Disclaimer

This is a **personal hobby project**, not affiliated with or endorsed by Themo. It is
provided **as is**, with **no warranty and no guarantee of fitness, correctness, or that it
works at all**. The author accepts **no liability** for any damage, data loss, unexpected
heating behaviour, energy cost, or any other consequence arising from its use. Use it
entirely at your own risk. See [LICENSE](LICENSE) for the full terms.

## Features

- **Climate** per thermostat: Off / Heat (Manual) / Auto (schedule) modes, target temperature,
  current temperature, and heating action.
- **Schedules**: switch the active heating schedule per thermostat from the climate **preset**
  selector ("Home" / "Away" etc.). A read-only websocket command exposes the full weekly
  setpoint grid for custom cards.
- **Sensors**: room temperature, floor temperature (only when the device has a floor sensor),
  and outside temperature.
- **Light**: thermostat backlight on/off.
- **Heating activity**: a binary sensor per thermostat showing whether the heating element is
  on right now.
- **Daily heating %**: two sensors per thermostat — a **running** share of the elapsed day and
  a **cumulative** share of the full 24 h — both reset at local midnight. Computed directly
  from on/off time, independent of the configured element power.
- **Energy**: hourly consumption imported as Home Assistant long-term statistics (with up to
  14 days of backfill), one per thermostat, for the Energy dashboard.

## Requirements

- Home Assistant 2025.1.0 or newer.
- A Themo account (the same email and password you use in the Themo app).

## Installation

### HACS (recommended)

1. In Home Assistant, open **HACS**.
2. Open the three-dot menu -> **Custom repositories**.
3. Add `https://github.com/jnaatanen/pd-hathemo` with category **Integration**.
4. Install **PapaDog's Home Assistant Themo Integration**.
5. Restart Home Assistant.

### Manual

1. Copy `custom_components/pd_hathemo` into your Home Assistant `config/custom_components/`
   directory.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings -> Devices & Services -> Add Integration**.
2. Search for **Themo** and select it.
3. Enter your Themo account email and password.

Each thermostat is added as a device with a climate entity, temperature sensors, and a
backlight light.

## Energy dashboard

After setup, each thermostat reports hourly consumption as a long-term statistic named
`<room> energy` (unit kWh). To see it:

1. Go to **Settings -> Dashboards -> Energy**.
2. Add each `<room> energy` statistic as a consumption source.

Up to 14 days of history is backfilled on first run; the Energy dashboard may take a couple
of hours to render newly added sources.

## Heating activity

Each thermostat exposes a `<room> Heating` binary sensor (on while the element is heating)
and two daily percentage sensors (running and cumulative) that **reset at local midnight**.

The percentage sensors cover the current day only. For longer periods — e.g. weekly or
monthly heating time — add a Home Assistant **History Stats** helper on the
`<room> Heating` binary sensor with your chosen start/end and `type: time` (hours on) or
`type: ratio` (percentage). The binary sensor is the source of truth; build whatever
longer-term meter or sensor best fits your needs on top of it.

## Schedules

Each thermostat's named heating schedules (the `MinTemperature` programs, e.g. "Home" /
"Away") are exposed as climate **presets**. Select a preset on the climate entity — or call
`climate.set_preset_mode` from an automation — to activate that schedule. Activating one
schedule deactivates the previously active one.

For custom cards, a read-only websocket command returns the full weekly setpoint grid:

```js
const result = await hass.connection.sendMessagePromise({
  type: "pd_hathemo/schedules",
  device_id: 28920,        // the Themo device id
});
// result.schedules: [{ id, name, parameter, unit, active,
//   setpoints: [{ day, hour, value }, ...] }]   // day 0=Sun..6=Sat, hour 0-23, value in C
```

## Notes

- The integration is **cloud polling**: device state is read every ~2 minutes, energy
  statistics every ~10 minutes, and schedules every ~15 minutes.
- Control commands (temperature, mode, backlight) are applied **optimistically** because the
  Themo cloud reflects commanded state with a delay.

## Roadmap

Possible future additions (not yet implemented):

- **Schedule setpoint editing** — the integration currently lets you switch the active
  schedule; editing the weekly setpoints (the `Day/Hour/Value` grid) from Home Assistant or a
  card is a possible future addition.

## License

[MIT](LICENSE) (c) Jouko Naatanen.
