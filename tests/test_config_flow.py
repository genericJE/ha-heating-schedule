"""Config flow happy path for Heating Schedule."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

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


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """User walks the wizard for a single room and lands on the summary."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"room_count": 1})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "room"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Bedroom",
            CONF_CLIMATE_ENTITY: "climate.bedroom",
            CONF_COMFORT_DEFAULT: DEFAULT_COMFORT,
            "window_count": 1,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "globals"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SETBACK: DEFAULT_SETBACK}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "summary"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Heating Schedule"
    assert result["data"][CONF_SETBACK] == DEFAULT_SETBACK
    rooms = result["data"][CONF_ROOMS]
    assert len(rooms) == 1
    assert rooms[0][CONF_NAME] == "Bedroom"
    assert rooms[0][CONF_CLIMATE_ENTITY] == "climate.bedroom"


async def test_add_room_step_when_entry_exists(hass: HomeAssistant) -> None:
    """Re-triggering the user flow on an existing entry routes to add_room."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
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
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_room"
