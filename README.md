# Heating Window Slider Card for Home Assistant

> **Personal project** — built for a specific Vaillant + Better Thermostat setup. Released as-is; works for me, may need adapting for your installation.

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

A per-room heating schedule for Home Assistant. Each room gets a card with a 24-hour shared track that holds **1 to 4 heating windows**, a target-temperature spinner, the current room temperature, and a window open/closed indicator. A single automation enforces the schedule against `climate` entities (designed for Better Thermostat, works against any climate that accepts `set_temperature`).

![Two schedule cards: Kitchen (active, window open) and Bedroom (inactive)](docs/schedule.png)

## What it gives you

- **1–4 windows per room** on a single 24h track. Add / remove via `+` and `−` buttons.
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
- One `climate` entity per room. Tested with [Better Thermostat](https://github.com/KartoffelToby/better_thermostat) wrapping Zigbee TRVs.
- Optional but recommended: per-room temperature sensor and window-opening binary sensor.

## Installation

### 1. The card

**HACS (custom repository)**

1. HACS → Frontend → ⋮ → Custom repositories
2. Add this repo's URL, category `Lovelace`
3. Install *Heating Window Slider Card*
4. Reload your browser

**Manual**

1. Copy `heating-window-slider-card.js` into `<config>/www/`
2. Settings → Dashboards → Resources → Add resource
   - URL: `/local/heating-window-slider-card.js`
   - Type: JavaScript module

### 2. Helpers

Merge the contents of [`examples/helpers.yaml`](examples/helpers.yaml) into your `configuration.yaml` (or wherever you keep `input_text:` and `input_number:` blocks). Then:

- Developer Tools → Services → `input_text.reload`
- Developer Tools → Services → `input_number.reload`

Each room gets:

- `input_text.heating_windows_<room>` — JSON array of `["HH:MM","HH:MM"]` window pairs. Defaults to one window with sensible day/night times.
- `input_number.heating_comfort_<room>` — comfort target (5–30 °C, step 0.5). Defaults to 20 °C (21 °C for the bedroom).

### 3. The automation

Copy [`examples/automation.yaml`](examples/automation.yaml) into your `automations.yaml`. The action's `variables.rooms` list and the per-room state triggers hard-code `kitchen`, `bedroom`, `bathroom`, `living_room`. Adapt to your installation's room slugs if they differ.

Then: Developer Tools → Services → `automation.reload`.

### 4. The dashboard

Add the cards from [`examples/dashboard.yaml`](examples/dashboard.yaml) to a sections-style view. Update each card's `entity_id`s to point at your installation.

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
- The `+` button finds the largest gap **between adjacent windows** and inserts a new window in the middle of it.
- The `−` button removes the latest (last-started) window. Min 1, max 4.

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

- Open-window detection — Better Thermostat handles that locally if you've enabled it. The card just surfaces window state for awareness.
- HVAC mode switching (heat / off / auto). The automation writes only `set_temperature`; mode stays where you put it.
- Holidays, geo fencing, presence-aware adjustments. Hook these into the existing pause flow rather than the schedule.

## License

MIT
