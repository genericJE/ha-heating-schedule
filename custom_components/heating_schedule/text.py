"""Text platform: per-room JSON window list."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from ._windows import is_unusable, validated_windows_json
from .const import (
    CONF_NAME,
    CONF_ROOMS,
    CONF_SLUG,
    CONF_WINDOWS_DEFAULT,
    DEFAULT_WINDOWS_JSON,
)
from .entity import HeatingScheduleRoomEntity

if TYPE_CHECKING:
    from . import HeatingScheduleConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatingScheduleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the text entities for each room."""
    rooms = entry.data.get(CONF_ROOMS, [])
    async_add_entities(
        HeatingWindowsText(
            entry,
            slug=room[CONF_SLUG],
            room_name=room[CONF_NAME],
            initial_json=room.get(CONF_WINDOWS_DEFAULT, DEFAULT_WINDOWS_JSON),
        )
        for room in rooms
    )


class HeatingWindowsText(HeatingScheduleRoomEntity, TextEntity, RestoreEntity):
    """JSON-encoded list of heating windows for a room.

    Entity ID is text.<room_slug>_windows (HA derives it from the device
    name and the translation key). Schedule controller resolves it via the
    entity registry by unique_id, so the device-derived slug doesn't have
    to match the slug in entry.data.

    Hidden by default — the device page surfaces the per-window time pickers
    instead, which are friendlier to edit than raw JSON. The text entity
    keeps existing for backwards-compat and as the canonical source of truth
    the card reads from.
    """

    _attr_translation_key = "windows"
    _attr_mode = TextMode.TEXT
    _attr_native_min = 0
    _attr_native_max = 255
    _attr_icon = "mdi:calendar-clock"
    _attr_entity_registry_visible_default = False

    def __init__(
        self,
        entry: HeatingScheduleConfigEntry,
        slug: str,
        room_name: str,
        initial_json: str,
    ) -> None:
        super().__init__(entry, slug, room_name)
        self._attr_unique_id = f"{entry.entry_id}_{slug}_windows"
        self._attr_native_value = validated_windows_json(initial_json, DEFAULT_WINDOWS_JSON)
        # Detach from the room device entirely so it doesn't clutter the
        # device's controls modal (where the time pickers + comfort are the
        # editing surface). The entity stays in the entity registry and the
        # card + time entities keep reading/writing its JSON.
        self._attr_device_info = None

    @property
    def suggested_object_id(self) -> str | None:
        # Without a device, HA would otherwise derive the entity_id from the
        # translated name ("Windows" → text.windows, collides across rooms).
        # Anchor it on the room slug so each room gets text.<slug>_windows.
        return f"{self._slug}_windows"

    async def async_added_to_hass(self) -> None:
        """Restore last known value or fall back to the configured default."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and not is_unusable(last.state):
            self._attr_native_value = validated_windows_json(last.state, DEFAULT_WINDOWS_JSON)

    async def async_set_value(self, value: str) -> None:
        """Validate and store a new JSON window list."""
        validated = validated_windows_json(value, DEFAULT_WINDOWS_JSON)
        if validated != self._attr_native_value:
            self._attr_native_value = validated
            self.async_write_ha_state()
