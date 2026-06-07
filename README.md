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
- **Sensors**: room temperature, floor temperature (only when the device has a floor sensor),
  and outside temperature.
- **Light**: thermostat backlight on/off.
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

## Notes

- The integration is **cloud polling**: device state is read every ~2 minutes and energy
  statistics are imported every ~10 minutes.
- Control commands (temperature, mode, backlight) are applied **optimistically** because the
  Themo cloud reflects commanded state with a delay.

## Roadmap

Possible future additions (not yet implemented):

- **Schedule switching** — Themo supports multiple named heating schedules per
  thermostat (e.g. "Home", "Away"). A future version could expose the active schedule
  as a climate `preset_mode`, so schedules can be switched directly from Home Assistant.
  (Themo allows one active schedule per parameter, which the implementation would need to
  account for.)
- **Heating activity ("heating now")** — Each thermostat reports whether its heating
  element is currently on or off. A future version could expose this as a `binary_sensor`
  per room, from which Home Assistant's History Stats can show how much of the day each
  room has been heating. (Because the element is simply on/off, an accurate daily
  duty-cycle can also be derived from the already-imported hourly energy divided by the
  element's rated power.)

## License

[MIT](LICENSE) (c) Jouko Naatanen.
