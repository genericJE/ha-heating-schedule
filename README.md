# Heating Window Slider Card for Home Assistant

> **Personal project** — built for a specific Vaillant + Better Thermostat setup. Released as-is; works for me, may need adapting for your installation.

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

A per-room heating schedule for Home Assistant. Each room gets a card with a 24-hour dual-handle slider for its heating window, a target-temperature spinner, the current room temperature, and a window open/closed indicator. A single automation enforces the schedule against `climate` entities (designed for Better Thermostat, works against any climate that accepts `set_temperature`).

## What it gives you

- **Per-room time windows** with a dual-handle range slider. Drag start and end on a 24-hour track; the window wraps around midnight when start is after end (e.g. 22:00 → 07:00 for a bedroom).
- **Per-room comfort temperature** via a `+/–` spinner — the room heats to this value inside the window.
- **Setback outside the window** — `14 °C` (Vaillant Frostschutz), hard-coded in the automation. Change it to taste.
- **Active / inactive badge** showing whether the current time is inside the window.
- **Current room temperature** in the subtitle, from a sensor you wire up.
- **Window open/closed icon** mirroring the colour theme of HA's tile cards (cyan when open).
- **`heating_paused` aware** — yields to the existing pause/resume flow with a 5 s delay so the schedule re-asserts after the snapshot restore, not against it.

## Requirements

- Home Assistant 2024.x or later (the card uses `ha-icon` and the automation uses the modern `triggers:` / `actions:` keys).
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

Merge the contents of [`examples/helpers.yaml`](examples/helpers.yaml) into your `configuration.yaml` (or wherever you keep `input_datetime:` and `input_number:` blocks). Then:

- Developer Tools → Services → `input_datetime.reload`
- Developer Tools → Services → `input_number.reload`

The defaults are sensible for a 4-room flat: bedroom heats at night (22:00 → 07:00), other rooms heat during the day. Comfort defaults are 20 °C / 21 °C for the bedroom.

### 3. The automation

Copy [`examples/automation.yaml`](examples/automation.yaml) into your `automations.yaml`. Edit the room list inside the action's `variables.rooms` template and the per-room `trigger.id` blocks to match your installation if your room slugs differ from `kitchen`, `bedroom`, `bathroom`, `living_room`.

Then: Developer Tools → Services → `automation.reload`.

### 4. The dashboard

Add the cards from [`examples/dashboard.yaml`](examples/dashboard.yaml) to a sections-style view. Update each card's `entity_id`s to point at your installation.

## Card config reference

```yaml
type: custom:heating-window-slider-card
name: Bedroom                              # optional, defaults to start_entity friendly name
start_entity: input_datetime.x             # required, time-only input_datetime
end_entity: input_datetime.y               # required, time-only input_datetime
comfort_entity: input_number.z             # required, comfort temperature
climate_entity: climate.bedroom_heating    # optional, shown in subtitle (hvac_action) and badge
current_temp_entity: sensor.bedroom_temp   # optional, current room temp in subtitle
window_entity: binary_sensor.bedroom_open  # optional, open/closed icon (cyan when open)
step_minutes: 5                            # optional, slider snap (default 5)
```

## How the schedule logic works

The automation is **edge-triggered**: it writes a climate target only when something changes that should change the target.

Triggers per room:

- Window **start** time arrives → in window → write comfort temp
- Window **end** time arrives → out of window → write setback (14 °C)
- The room's `input_datetime` or `input_number` helper state changes (slider drag, spinner click) → re-evaluate immediately

Plus two global triggers:

- `homeassistant.start` → evaluate all 4 rooms after a 5 s settle delay
- `input_boolean.heating_paused` goes off → evaluate all 4 rooms after a 5 s settle delay (lets `Resume Heating on Return` finish its scene restore first)

Window-membership math (handles the wrap-around):

```
in_window = (start < end  and start ≤ now < end)
         or (start > end  and (now ≥ start or now < end))
```

`start == end` is treated as "never heat" (zero-width window).

Each room's write is guarded by `current_target ≠ desired`, so the automation is idempotent — re-evaluations that match the current target are no-ops and won't churn the TRV.

## Integration with `heating_paused` / `Resume Heating`

The flow assumes the same shape as my installation:

- **Apply Heating Pause** on `heating_paused: off → on` — snapshots `scene.heating_pause_snapshot`, sets all rooms to 14 °C.
- **Resume Heating on Return** on `eta ≤ now` — turns `heating_paused` off, restores from the scene, 3 s settle, then optional Hc1DayTemp fallback.

This automation includes a 5 s delay on the "all rooms" branch (triggered by `heating_paused` off-transition or HA start) so Resume's scene restore lands before the schedule re-asserts. The idempotent write guard keeps things quiet when the scene's restored values already match the schedule's desired state.

If a user manually un-pauses (without Resume firing, e.g. by tapping the Pause button), the schedule simply writes comfort/setback after the 5 s delay — no scene needed.

**Semantics**: pre-pause manual climate-target overrides do not survive across a pause. The schedule wins on resume. If you'd rather have manual overrides persist, remove the `heating_paused` state trigger from the automation; the next window edge will reassert the schedule anyway.

## Customisation

- **Comfort temperature**: it's a per-room `input_number`. Adjust via the spinner or directly in the helper.
- **Setback temperature**: hard-coded as `14` in the automation's `variables.setback`. Change it there.
- **Slider step**: pass `step_minutes: 15` (or other) on the card to coarsen the granularity. Defaults to 5.
- **Comfort defaults per room**: in `helpers.yaml`, the `initial:` keys set the value used the first time the helper loads.

## Not in scope

- Open-window detection — Better Thermostat handles that locally if you've enabled it. The card just surfaces window state for awareness.
- HVAC mode switching (heat / off / auto). The automation writes only `set_temperature`; mode stays where you put it.
- Holidays, geo fencing, presence-aware adjustments. Hook these into the existing pause flow rather than the schedule.

## License

MIT
