"""Number platform: per-room comfort temperature + heating-window count."""

from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from ._windows import is_unusable, parse_windows, resize_windows
from .const import (
    CONF_COMFORT_DEFAULT,
    CONF_NAME,
    CONF_ROOMS,
    CONF_SETBACK,
    CONF_SLUG,
    DEFAULT_COMFORT,
    DEFAULT_COMFORT_MAX,
    DEFAULT_COMFORT_MIN,
    DEFAULT_COMFORT_STEP,
    DEFAULT_SETBACK,
    MAX_WINDOWS,
    SETBACK_UNIQUE_SUFFIX,
)
from .entity import HeatingScheduleRoomEntity, hub_device_info

if TYPE_CHECKING:
    from . import HeatingScheduleConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatingScheduleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the comfort + window-count number entities for each room,
    plus the hub-level setback temperature."""
    entities: list[NumberEntity] = [
        HeatingSetbackNumber(
            entry,
            initial_value=float(entry.data.get(CONF_SETBACK, DEFAULT_SETBACK)),
        )
    ]
    for room in entry.data.get(CONF_ROOMS, []):
        slug = room[CONF_SLUG]
        room_name = room[CONF_NAME]
        entities.append(
            HeatingComfortNumber(
                entry,
                slug=slug,
                room_name=room_name,
                initial_value=float(room.get(CONF_COMFORT_DEFAULT, DEFAULT_COMFORT)),
            )
        )
        entities.append(HeatingWindowCountNumber(entry, slug=slug, room_name=room_name))
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

    @property
    def suggested_object_id(self) -> str | None:
        # HA prepends the device name for has_entity_name entities, so just
        # return the suffix. Result: number.<slug>_comfort regardless of how
        # the "Comfort" translation gets rendered.
        return "comfort"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and not is_unusable(last.state):
            with contextlib.suppress(TypeError, ValueError):
                self._attr_native_value = _clamp(float(last.state))

    async def async_set_native_value(self, value: float) -> None:
        clamped = _clamp(value)
        if clamped != self._attr_native_value:
            self._attr_native_value = clamped
            self.async_write_ha_state()


class HeatingWindowCountNumber(HeatingScheduleRoomEntity, NumberEntity):
    """How many heating windows the room schedule should have.

    Backed by the text entity's JSON array length. Writes resize the JSON
    via text.set_value, mirroring the card editor's window_count slider:
    truncate when shrinking, place_new_window in the largest cyclic gap
    when growing.
    """

    _attr_translation_key = "window_count"
    _attr_native_min_value = 1
    _attr_native_max_value = MAX_WINDOWS
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:calendar-multiple"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        entry: HeatingScheduleConfigEntry,
        slug: str,
        room_name: str,
    ) -> None:
        super().__init__(entry, slug, room_name)
        self._attr_unique_id = f"{entry.entry_id}_{slug}_window_count"

    @property
    def suggested_object_id(self) -> str | None:
        # Pre-existing rooms have number.<slug>_number_of_heating_windows
        # (slugified from the original "Number of heating windows" name);
        # those entity IDs are sticky in the registry. For new rooms this
        # makes the ID number.<slug>_window_count, decoupled from whatever
        # the translated label looks like.
        return "window_count"

    @property
    def _windows_entity_id(self) -> str:
        return f"text.{self._slug}_windows"

    @property
    def native_value(self) -> int | None:
        if self.hass is None:
            return None
        state = self.hass.states.get(self._windows_entity_id)
        if state is None or is_unusable(state.state):
            return None
        count = len(parse_windows(state.state))
        return count or None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Re-render when the text entity's JSON changes (drag in card, edit
        # in card editor, time-picker write, etc).
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._windows_entity_id], self._on_text_change
            )
        )

    @callback
    def _on_text_change(self, _event: Event[EventStateChangedData]) -> None:
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        target = max(1, min(MAX_WINDOWS, int(value)))
        state = self.hass.states.get(self._windows_entity_id)
        existing = parse_windows(state.state if state else None)
        if len(existing) == target:
            return
        new = resize_windows(existing, target)
        await self.hass.services.async_call(
            "text",
            "set_value",
            {"entity_id": self._windows_entity_id, "value": json.dumps(new)},
            blocking=False,
        )


class HeatingSetbackNumber(NumberEntity, RestoreEntity):
    """Setback temperature applied outside any heating window.

    Hub-scoped (one per config entry). Initial value is seeded from the
    wizard's setback step; state is restored across restarts. The schedule
    controller reads its state on every evaluation, so adjusting it from
    a dashboard tile or automation takes effect on the next tick (and
    immediately via a state-change subscription).
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "setback"
    _attr_native_min_value = DEFAULT_COMFORT_MIN
    _attr_native_max_value = DEFAULT_COMFORT_MAX
    _attr_native_step = DEFAULT_COMFORT_STEP
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:thermometer-low"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        entry: HeatingScheduleConfigEntry,
        initial_value: float,
    ) -> None:
        super().__init__()
        self._attr_unique_id = f"{entry.entry_id}_{SETBACK_UNIQUE_SUFFIX}"
        self._attr_native_value = _clamp(initial_value)
        self._attr_device_info = hub_device_info(entry)

    @property
    def suggested_object_id(self) -> str | None:
        # Yields number.heating_schedule_setback regardless of translation.
        return f"heating_schedule_{SETBACK_UNIQUE_SUFFIX}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and not is_unusable(last.state):
            with contextlib.suppress(TypeError, ValueError):
                self._attr_native_value = _clamp(float(last.state))

    async def async_set_native_value(self, value: float) -> None:
        clamped = _clamp(value)
        if clamped != self._attr_native_value:
            self._attr_native_value = clamped
            self.async_write_ha_state()


def _clamp(value: float) -> float:
    return max(DEFAULT_COMFORT_MIN, min(DEFAULT_COMFORT_MAX, value))
