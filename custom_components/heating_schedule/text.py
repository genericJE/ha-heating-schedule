"""Text platform: per-room JSON window list."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_NAME,
    CONF_ROOMS,
    CONF_SLUG,
    CONF_WINDOWS_DEFAULT,
    DEFAULT_WINDOWS_JSON,
    MAX_WINDOWS,
)
from .entity import HeatingScheduleRoomEntity

if TYPE_CHECKING:
    from . import HeatingScheduleConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatingScheduleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the text entities for each room."""
    rooms = entry.data.get(CONF_ROOMS, [])
    entities = [
        HeatingWindowsText(
            entry,
            slug=room[CONF_SLUG],
            room_name=room[CONF_NAME],
            initial_json=room.get(CONF_WINDOWS_DEFAULT, DEFAULT_WINDOWS_JSON),
        )
        for room in rooms
    ]
    async_add_entities(entities)


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
        self._attr_native_value = _validated_or_default(initial_json)
        # Detach from the room device entirely so it doesn't clutter the
        # device's controls modal (where the time pickers + comfort are the
        # editing surface). The entity stays in the entity registry and the
        # card + time entities keep reading/writing its JSON.
        self._attr_device_info = None

    async def async_added_to_hass(self) -> None:
        """Restore last known value or fall back to the configured default."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in (None, "", "unknown", "unavailable"):
            self._attr_native_value = _validated_or_default(last.state)

    async def async_set_value(self, value: str) -> None:
        """Validate and store a new JSON window list."""
        validated = _validated_or_default(value)
        if validated != self._attr_native_value:
            self._attr_native_value = validated
            self.async_write_ha_state()


def _validated_or_default(raw: str) -> str:
    """Return raw if it's a valid JSON window list (1..MAX_WINDOWS), else default."""
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return DEFAULT_WINDOWS_JSON
    if not isinstance(parsed, list) or not parsed or len(parsed) > MAX_WINDOWS:
        return DEFAULT_WINDOWS_JSON
    cleaned: list[list[str]] = []
    for item in parsed:
        if not (isinstance(item, list) and len(item) == 2):
            return DEFAULT_WINDOWS_JSON
        a, b = item
        if not (_is_hhmm(a) and _is_hhmm(b)):
            return DEFAULT_WINDOWS_JSON
        cleaned.append([a, b])
    return json.dumps(cleaned)


def _is_hhmm(s: object) -> bool:
    if not isinstance(s, str) or len(s) != 5 or s[2] != ":":
        return False
    try:
        h = int(s[:2])
        m = int(s[3:])
    except ValueError:
        return False
    return 0 <= h <= 23 and 0 <= m <= 59
