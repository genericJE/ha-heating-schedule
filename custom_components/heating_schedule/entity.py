"""Base entity for the Heating Schedule integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN

if TYPE_CHECKING:
    from . import HeatingScheduleConfigEntry


class HeatingScheduleRoomEntity(Entity):
    """Base for per-room entities owned by the integration."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        entry: HeatingScheduleConfigEntry,
        slug: str,
        room_name: str,
    ) -> None:
        super().__init__()
        self._entry = entry
        self._slug = slug
        self._room_name = room_name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{slug}")},
            name=room_name,
            manufacturer="Heating Schedule",
            model="Room schedule",
            entry_type=None,
        )
