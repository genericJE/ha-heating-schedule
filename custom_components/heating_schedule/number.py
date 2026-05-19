"""Number platform: per-room comfort temperature."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_COMFORT_DEFAULT,
    CONF_NAME,
    CONF_ROOMS,
    CONF_SLUG,
    DEFAULT_COMFORT,
    DEFAULT_COMFORT_MAX,
    DEFAULT_COMFORT_MIN,
    DEFAULT_COMFORT_STEP,
)
from .entity import HeatingScheduleRoomEntity

if TYPE_CHECKING:
    from . import HeatingScheduleConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatingScheduleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the comfort-temperature number entities."""
    rooms = entry.data.get(CONF_ROOMS, [])
    entities = [
        HeatingComfortNumber(
            entry,
            slug=room[CONF_SLUG],
            room_name=room[CONF_NAME],
            initial_value=float(room.get(CONF_COMFORT_DEFAULT, DEFAULT_COMFORT)),
        )
        for room in rooms
    ]
    async_add_entities(entities)


class HeatingComfortNumber(HeatingScheduleRoomEntity, NumberEntity, RestoreEntity):
    """Comfort temperature target for a room."""

    _attr_translation_key = "comfort"
    _attr_native_min_value = DEFAULT_COMFORT_MIN
    _attr_native_max_value = DEFAULT_COMFORT_MAX
    _attr_native_step = DEFAULT_COMFORT_STEP
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:thermometer"

    def __init__(
        self,
        entry: HeatingScheduleConfigEntry,
        slug: str,
        room_name: str,
        initial_value: float,
    ) -> None:
        super().__init__(entry, slug, room_name)
        self._attr_unique_id = f"{entry.entry_id}_{slug}_comfort"
        self._attr_native_value = _clamp(initial_value)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in (None, "", "unknown", "unavailable"):
            try:
                self._attr_native_value = _clamp(float(last.state))
            except (TypeError, ValueError):
                pass

    async def async_set_native_value(self, value: float) -> None:
        clamped = _clamp(value)
        if clamped != self._attr_native_value:
            self._attr_native_value = clamped
            self.async_write_ha_state()


def _clamp(value: float) -> float:
    return max(DEFAULT_COMFORT_MIN, min(DEFAULT_COMFORT_MAX, value))
