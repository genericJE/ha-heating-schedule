"""Setup + unload lifecycle for Heating Schedule."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

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


def _make_entry() -> MockConfigEntry:
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
                    "windows_default": '[["07:00","22:00"]]',
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


async def test_skip_when_climate_off(hass: HomeAssistant) -> None:
    """A climate in hvac_mode=off must not be written to."""
    hass.states.async_set("climate.bedroom", STATE_OFF, {"temperature": 5.0})

    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("climate.bedroom")
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes.get("temperature") == 5.0

    await hass.config_entries.async_unload(entry.entry_id)
