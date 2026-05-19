# Heating Window Slider Card for Home Assistant

> **Personal project** — built for a specific Vaillant + Better Thermostat installation. The card and automation only depend on a `climate` entity that accepts `set_temperature`, so they work with any climate integration; the rest of the install is generic HA. Released as-is.

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

A per-room heating schedule for Home Assistant. Each room gets a card with a 24-hour shared track that holds **1 to 4 heating windows**, a target-temperature spinner, the current room temperature, and a window open/closed indicator. A single automation enforces the schedule against `climate` entities (designed for Better Thermostat, works against any climate that accepts `set_temperature`).

![Two schedule cards: Kitchen (active, window open) and Bedroom (inactive)](docs/schedule.png)

## What it gives you

- **1–4 windows per room** on a single 24h track. Window count is configuration only — set by the length of the JSON list in the helper (or its `initial:` default in `helpers.yaml`). To add or remove a window: edit the `input_text` helper value.
- **Dual-handle range slider per window**. Drag start and end; cyclic neighbour constraint prevents handles from passing one another (equal values are allowed for smooth touching).
- **Wrap-around for the last window**: if its end is earlier than its start (e.g. `22:00 → 07:00`), it renders as two fills (start→24:00 and 00:00→end). Wrap is reachable through ordinary drags — no special toggle.
- **Per-room comfort temperature** via a `+/–` spinner. The room heats to this value whenever any window is active.
- **Setback outside all windows**: 14 °C (Vaillant Frostschutz), hard-coded in the automation. Change it to taste.
- **Active / inactive badge** — whether the current time falls inside any window for that room.
- **Current room temperature** in the subtitle, from a sensor you wire up.
- **Window open/closed icon** mirroring the colour theme of HA's tile cards (cyan when open).
- **`heating_paused` aware** — yields to the existing pause/resume flow with a 5 s delay so the schedule re-asserts after the snapshot restore, not against it.

## Requirements

- Home Assistant 2024.x or later (the card uses `ha-icon` and the automation uses the modern `triggers:` / `actions:` keys, plus the `from_json` filter).
- One `climate` entity per room that accepts `set_temperature` — any climate integration works (Better Thermostat, generic_thermostat, MQTT HVAC, native Zigbee TRV climates, etc.). I happen to use [Better Thermostat](https://github.com/KartoffelToby/better_thermostat) over Zigbee TRVs, which is why the install notes occasionally reference it.
- Optional but recommended: per-room temperature sensor and window-opening binary sensor.

## Installation

Pick **one** path. The integration is the hands-off route; the YAML path is what existed before and still works.

### A. Via the integration (recommended)

This installs the card *and* provisions everything else — per-room window storage, comfort target, the schedule controller — through a normal HA config flow.

1. **HACS** → ⋮ → *Custom repositories* → add this repo's URL, type **Integration**, install *Heating Schedule*. Restart HA.
2. **Settings → Devices & Services → Add Integration → "Heating Schedule"**. The wizard asks for the number of rooms, then per room: name + climate entity (+ optional current-temperature sensor and window binary sensor) + comfort temperature + initial windows. The last step shows a pasteable Lovelace YAML snippet for a sections view.
3. **Settings → Dashboards → Resources → Add resource** → URL `/heating_schedule/heating-window-slider-card.js`, type *JavaScript module*. (One-time. The integration serves the card from its own static path.)
4. Paste the YAML snippet into a sections-style dashboard view.

Per room you get:

- `text.heating_schedule_windows_<slug>` — JSON window list, written by the card slider.
- `number.heating_schedule_comfort_<slug>` — comfort target, written by the card spinner.

The schedule controller runs inside the integration (per-minute tick + state-change listeners + HA start + optional `input_boolean.heating_paused` off-transition with a 5 s settle). It writes `set_temperature` to your climate entity when in-window and the configured setback otherwise, with an idempotent guard so unchanged targets stay quiet.

### B. Manual YAML install (the original path)

If you'd rather wire the helpers and the automation up by hand — useful if you already have a YAML-only install and don't want to migrate — the original path is unchanged:

1. **Card**: copy [`custom_components/heating_schedule/www/heating-window-slider-card.js`](custom_components/heating_schedule/www/heating-window-slider-card.js) into `<config>/www/`, then *Settings → Dashboards → Resources → Add resource* with URL `/local/heating-window-slider-card.js`, type *JavaScript module*.
2. **Helpers**: merge [`examples/helpers.yaml`](examples/helpers.yaml) into `configuration.yaml`, then call `input_text.reload` and `input_number.reload`.
3. **Automation**: copy [`examples/automation.yaml`](examples/automation.yaml) into `automations.yaml` (adapting the room slugs if they differ from `kitchen` / `bedroom` / `bathroom` / `living_room`), then call `automation.reload`.
4. **Dashboard**: add the cards from [`examples/dashboard.yaml`](examples/dashboard.yaml) to a sections view, pointing each card's entities at your installation.

The card auto-detects the entity domain (`input_text` vs `text`, `input_number` vs `number`) and calls the matching `set_value` service, so the same card binary works for both paths.

## Card config reference

```yaml
type: custom:heating-window-slider-card
name: Bedroom                              # optional, defaults to entity friendly name
windows_entity: input_text.x               # required, JSON array of HH:MM pairs
comfort_entity: input_number.y             # required, comfort temperature
climate_entity: climate.bedroom_heating    # optional, drives subtitle + heating tint
current_temp_entity: sensor.bedroom_temp   # optional, current room temp in subtitle
window_entity: binary_sensor.bedroom_open  # optional, open/closed icon (cyan when open)
step_minutes: 5                            # optional, slider snap (default 5)
```

## How the schedule logic works

The automation runs every minute (`time_pattern: '/1'`) and also fires on:

- state change of any `input_text.heating_windows_<room>` (slider drag, add/remove window)
- state change of any `input_number.heating_comfort_<room>` (spinner click)
- `input_boolean.heating_paused` off→on transitions (with a 5 s settle delay)
- `homeassistant.start`

For each room it parses the JSON window list and checks whether **any** window contains the current time. The window-membership math (with wrap):

```
in_window = (s < e  and s ≤ n < e)
         or (s > e  and (n ≥ s or n < e))
```

If yes → write `comfort_<room>` to the climate target. If no → write `14 °C` (setback).

Each write is guarded by `current_target ≠ desired`, so re-evaluations that match are no-ops and the TRV doesn't churn.

## Drag rules

- Each handle is clamped between its **cyclic neighbours** on the 24h circle (immediate prev / next handle clockwise).
- **Equal values are allowed** — two handles can touch but not pass.
- After every drag the schedule is **canonicalised** (sorted by start). If a drag causes a window to "wrap", the window ends up last in the list with `end < start`, and the slider renders both fill segments automatically. There's no separate wrap mode toggle.
- **Window count is configuration only.** The card has no `+` / `−` UI; the number of windows is the JSON array length in the `input_text` helper (1 to 4). To add or remove a window, edit the helper (Developer Tools → States, or call `input_text.set_value`).

## Integration with `heating_paused` / `Resume Heating`

The flow assumes the same shape as my installation:

- **Apply Heating Pause** on `heating_paused: off → on` — snapshots `scene.heating_pause_snapshot`, sets all rooms to 14 °C.
- **Resume Heating on Return** on `eta ≤ now` — turns `heating_paused` off, restores from the scene, 3 s settle, then optional Hc1DayTemp fallback.

This automation includes a 5 s delay on the "all rooms" branch (triggered by `heating_paused` off-transition or HA start) so Resume's scene restore lands before the schedule re-asserts. The idempotent write guard keeps things quiet when the scene's restored values already match the schedule's desired state.

If a user manually un-pauses (without Resume firing, e.g. by tapping the Pause button), the schedule simply writes comfort/setback after the 5 s delay — no scene needed.

**Semantics**: pre-pause manual climate-target overrides do not survive across a pause. The schedule wins on resume. If you'd rather have manual overrides persist, remove the `heating_paused` state trigger from the automation; the schedule will reassert on the next tick or helper change anyway.

## Customisation

- **Comfort temperature**: per-room `input_number`. Adjust via the spinner or directly in the helper.
- **Setback temperature**: hard-coded as `14` in the automation's `variables.setback`. Change it there.
- **Slider step**: pass `step_minutes: 15` (or other) on the card to coarsen the granularity. Default is 5.
- **Comfort defaults per room**: in `helpers.yaml`, the `initial:` keys set the value used the first time a helper loads.
- **Default windows**: also via `initial:` in `helpers.yaml`. The card and automation will follow.

## Not in scope

- Open-window detection — your climate integration may handle that locally (Better Thermostat does). The card just surfaces window state for awareness.
- HVAC mode switching (heat / off / auto). The automation writes only `set_temperature`; mode stays where you put it.
- Holidays, geo fencing, presence-aware adjustments. Hook these into the existing pause flow rather than the schedule.

## License

MIT
