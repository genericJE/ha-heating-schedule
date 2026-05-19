# Changelog

All notable changes to this project are documented here. Versioning follows [Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-05-19

First public release. HACS submission pending.

### Added

- Per-room heating windows on a 24h shared track (1–4 windows), dual-handle range slider with wrap-around.
- Custom Lovelace card `heating-window-slider-card` served from the integration's own static path.
- Config flow provisions per-room helpers (`text.<slug>_windows`, `number.<slug>_comfort`, `number.<slug>_window_count`) plus per-room time entities (`time.<slug>_window_<n>_start|end`) for device-page editing.
- Hub-level `switch.heating_schedule_pause` with bidirectional sync to `input_boolean.heating_paused`.
- Hub-level `number.heating_schedule_setback` (user-facing, default 14 °C, adjustable from a dashboard tile or service call).
- Schedule controller: per-minute tick + state-change listeners; respects `hvac_mode=off` and Better Thermostat window-open frost protect; idempotent climate writes.
- Add-room flow on already-configured entries.
- Per-room device removal via the "Delete device" button on the device page.
- 26 translations.
- Tests: config-flow happy path + setup/unload lifecycle.

### Requirements

- Home Assistant 2024.4 or later.
- One `climate` entity per room that accepts `set_temperature`.

[0.1.0]: https://github.com/genericJE/ha-heating-schedule/releases/tag/v0.1.0
