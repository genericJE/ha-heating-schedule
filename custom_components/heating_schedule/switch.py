"""Switch platform: integration-owned heating pause toggle.

Replaces the external input_boolean.heating_paused that the YAML setup
used. State is RestoreEntity-backed so a pause survives HA restarts.
The schedule controller listens for state changes via the entity
registry and applies setback on off->on, re-evaluates on on->off.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import PAUSE_UNIQUE_SUFFIX
from .entity import hub_device_info

if TYPE_CHECKING:
    from . import HeatingScheduleConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatingScheduleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the single pause switch for this entry."""
    async_add_entities([HeatingSchedulePauseSwitch(entry)])


class HeatingSchedulePauseSwitch(SwitchEntity, RestoreEntity):
    """The Heating Paused toggle, owned by the integration."""

    _attr_has_entity_name = True
    _attr_translation_key = "pause"
    _attr_icon = "mdi:pause-circle-outline"
    _attr_should_poll = False

    def __init__(self, entry: HeatingScheduleConfigEntry) -> None:
        super().__init__()
        self._attr_unique_id = f"{entry.entry_id}_{PAUSE_UNIQUE_SUFFIX}"
        self._attr_is_on = False
        self._attr_device_info = hub_device_info(entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in ("on", "off"):
            self._attr_is_on = last.state == "on"

    async def async_turn_on(self, **_: Any) -> None:
        if not self._attr_is_on:
            self._attr_is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **_: Any) -> None:
        if self._attr_is_on:
            self._attr_is_on = False
            self.async_write_ha_state()
