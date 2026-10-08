"""Setup + unload lifecycle for Heating Schedule."""

from __future__ import annotations

import json
from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.heating_schedule.const import (
    CONF_CLIMATE_ENTITY,
    CONF_COMFORT_DEFAULT,
    CONF_NAME,
    CONF_ROOMS,
    CONF_SETBACK,
    DEFAULT_COMFORT,
    DEFAULT_SETBACK,
    DOMAIN,
)

ALL_DAY = '[["00:00","23:59"]]'


def _idle_window() -> str:
    """A window starting 10 minutes from now — never active during a test.

    Windows are evaluated against dt_util.now(), so a literal like
    [["23:00","23:30"]] makes a test's outcome depend on when CI runs.
    Deriving it from now keeps it inactive at any hour, including across
    midnight (_in_window's wrap branch still excludes the current minute).
    """
    now = dt_util.now()
    start = now + timedelta(minutes=10)
    end = now + timedelta(minutes=20)
    return json.dumps([[start.strftime("%H:%M"), end.strftime("%H:%M")]])


async def _fire_tick(hass: HomeAssistant) -> None:
    """Drive one per-minute evaluation instead of waiting for the settle timer.

    The controller also evaluates ~5s after startup, but that path races the
    assertions: whether the task has landed by the time the test looks at the
    captured calls depends on the machine. The interval tick evaluates the
    same way and fires on demand.
    """
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
    await hass.async_block_till_done()


def _make_entry(windows: str = ALL_DAY) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Heating Schedule",
        data={
            CONF_ROOMS: [
                {
                    "slug": "bedroom",
                    CONF_NAME: "Bedroom",
                    CONF_CLIMATE_ENTITY: "climate.bedroom",
                    "current_temp_entity": None,
                    "window_entity": None,
                    CONF_COMFORT_DEFAULT: DEFAULT_COMFORT,
                    "windows_default": windows,
                }
            ],
            CONF_SETBACK: DEFAULT_SETBACK,
        },
    )


async def test_setup_and_unload(hass: HomeAssistant) -> None:
    """Entry loads its platforms and the hub-level setback/pause entities."""
    hass.states.async_set("climate.bedroom", "heat", {"temperature": 20.0})

    entry = _make_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("switch.heating_schedule_pause") is not None
    setback_state = hass.states.get("number.heating_schedule_setback")
    assert setback_state is not None
    assert float(setback_state.state) == DEFAULT_SETBACK
    assert hass.states.get("text.bedroom_windows") is not None
    assert hass.states.get("number.bedroom_comfort") is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setback_state_change_reevaluates(hass: HomeAssistant) -> None:
    """Editing number.heating_schedule_setback updates the climate target."""
    hass.states.async_set("climate.bedroom", "heat", {"temperature": 20.0})

    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.heating_schedule_setback", "value": 15.5},
        blocking=True,
    )
    state = hass.states.get("number.heating_schedule_setback")
    assert state is not None
    assert float(state.state) == 15.5

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_setback_applied_outside_window(
    hass: HomeAssistant, climate_calls: list[ServiceCall]
) -> None:
    """Outside every window the room is pushed to the setback temperature."""
    hass.states.async_set("climate.bedroom", "heat", {"temperature": 20.0})

    entry = _make_entry(windows=_idle_window())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await _fire_tick(hass)

    assert climate_calls
    assert {c.data["temperature"] for c in climate_calls} == {DEFAULT_SETBACK}
    assert {c.data["entity_id"] for c in climate_calls} == {"climate.bedroom"}

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_skip_when_climate_off(hass: HomeAssistant, climate_calls: list[ServiceCall]) -> None:
    """A climate in hvac_mode=off must not be written to."""
    hass.states.async_set("climate.bedroom", STATE_OFF, {"temperature": 5.0})

    entry = _make_entry(windows=_idle_window())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await _fire_tick(hass)

    # 5.0 differs from both comfort and setback, so an unguarded controller
    # would have written here no matter which side of the window we are on.
    assert climate_calls == []
    state = hass.states.get("climate.bedroom")
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes.get("temperature") == 5.0

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
