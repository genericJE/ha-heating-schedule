# Changelog

All notable changes to this project are documented here. Versioning follows [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-08

### Changed

- Minimum Home Assistant version is 2024.7. The card is served through the async static-path API that first shipped there; 0.1.0 claimed 2024.4, where the integration failed to import.
- Test suite and CI run on Python 3.14 against a 2026.x core. The previous lock pinned Home Assistant 2025.4, so CI could not see current deprecations.
- Config-flow summary notes that the pasted entity IDs assume Home Assistant's default entity ID format.
- The card's "static path registered" flag in `hass.data` is a typed `HassKey`.

### Fixed

- The 25 non-English translations gained the add-room step and the `room_added` abort text, which had only existed in English.
- Tests register `climate.set_temperature` themselves, so the suite no longer depends on the wall clock.
- The settle and pause-snapshot delays are entry background tasks. They are cancelled on unload and on shutdown instead of writing climate targets after the controller stopped and holding up Home Assistant's shutdown.

### Removed

- Unused `already_configured` abort string (the flow routes a second setup to the add-room step instead).

### Requirements

- Home Assistant 2024.7 or later.

## [0.1.1] - 2026-05-19

Re-cut of 0.1.0 for the HACS default submission, so the release sits on a validated workflow run. The manifest still reported 0.1.0.

### Added

- Brand icons served from `custom_components/heating_schedule/brand/` (the HA 2026.3 mechanism).
- CI workflow: hassfest, HACS and pytest validation.
- Tests for the config-flow happy path and the setup/unload lifecycle.

### Changed

- `iot_class` corrected to `local_polling`.
- README install step prefers HACS default, with the custom-repository route as fallback.

### Fixed

- Setback entity ID is no longer double-prefixed.

## [0.1.0] - 2026-05-19

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

[0.2.0]: https://github.com/genericJE/ha-heating-schedule/releases/tag/v0.2.0
[0.1.1]: https://github.com/genericJE/ha-heating-schedule/releases/tag/v0.1.1
[0.1.0]: https://github.com/genericJE/ha-heating-schedule/releases/tag/v0.1.0
