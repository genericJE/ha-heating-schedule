"""Time platform: per-window-edge time pickers backed by the windows JSON.

Each room exposes MAX_WINDOWS x 2 time entities (start + end for each
window slot). They read and write the same `text.<slug>_windows` JSON
that the card and the schedule controller use, so picking a time on the
device page propagates instantly to everything else.

Slots beyond the current window count are toggled `disabled_by="integration"`
by HeatingScheduleController so the device page only shows the entities
the user actually has windows for. When the count grows, the relevant
entities are re-enabled automatically.
"""

from __future__ import annotations

import json
import logging
from datetime import time
from typing import TYPE_CHECKING

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from ._windows import parse_windows
from .const import (
    CONF_NAME,
    CONF_ROOMS,
    CONF_SLUG,
    MAX_WINDOWS,
)
from .entity import HeatingScheduleRoomEntity

if TYPE_CHECKING:
    from . import HeatingScheduleConfigEntry

_LOGGER = logging.getLogger(__name__)

EDGES: tuple[str, ...] = ("start", "end")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatingScheduleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one time picker per (room, window slot, edge)."""
    async_add_entities(
        HeatingWindowEdgeTime(entry, room[CONF_SLUG], room[CONF_NAME], idx, edge)
        for room in entry.data.get(CONF_ROOMS, [])
        for idx in range(MAX_WINDOWS)
        for edge in EDGES
    )


class HeatingWindowEdgeTime(HeatingScheduleRoomEntity, TimeEntity):
    """One edge (start or end) of one window slot.

    Reads from `text.<slug>_windows`'s JSON state. Writes back to it
    through the text.set_value service so the schedule controller and
    the card see the same value.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        entry: HeatingScheduleConfigEntry,
        slug: str,
        room_name: str,
        window_idx: int,
        edge: str,
    ) -> None:
        super().__init__(entry, slug, room_name)
        self._window_idx = window_idx
        self._edge = edge
        self._edge_pos = 0 if edge == "start" else 1
        self._attr_unique_id = f"{entry.entry_id}_{slug}_window_{window_idx + 1}_{edge}"
        self._attr_translation_key = f"window_{window_idx + 1}_{edge}"
        # mdi:clock-start exists in mdi 7.4+; gives a visual hint for
        # start vs end that survives label truncation.
        self._attr_icon = "mdi:clock-start" if edge == "start" else "mdi:clock-end"
        # Off by default for slots beyond the first; controller flips
        # disabled_by on the registry to match the current window count.
        self._attr_entity_registry_enabled_default = window_idx == 0

    @property
    def suggested_object_id(self) -> str | None:
        # The symbolic "▶1"/"◼1" translations slugify to just "1" and collide
        # within a room. Anchor on the slot index + edge so new rooms get
        # time.<slug>_window_<n>_<start|end>, independent of label.
        return f"window_{self._window_idx + 1}_{self._edge}"

    @property
    def _windows_entity_id(self) -> str:
        return f"text.{self._slug}_windows"

    def _read_windows(self) -> list[list[str]]:
        if self.hass is None:
            return []
        state = self.hass.states.get(self._windows_entity_id)
        return parse_windows(state.state if state else None)

    @property
    def native_value(self) -> time | None:
        windows = self._read_windows()
        if self._window_idx >= len(windows):
            return None
        return _parse_hhmm(windows[self._window_idx][self._edge_pos])

    @property
    def available(self) -> bool:
        return self._window_idx < len(self._read_windows())

    async def async_added_to_hass(self) -> None:
        # Re-push our state whenever the backing text JSON changes (card drag,
        # window_count resize, restore). Without this the cached state stays
        # stale even though native_value would return the right value.
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._windows_entity_id], self._on_text_change
            )
        )

    @callback
    def _on_text_change(self, _event: Event[EventStateChangedData]) -> None:
        self.async_write_ha_state()

    async def async_set_value(self, value: time) -> None:
        windows = self._read_windows()
        if self._window_idx >= len(windows):
            _LOGGER.debug(
                "Refusing time write for %s: window %d is past count %d",
                self.entity_id,
                self._window_idx,
                len(windows),
            )
            return
        hhmm = f"{value.hour:02d}:{value.minute:02d}"
        if windows[self._window_idx][self._edge_pos] == hhmm:
            return
        windows[self._window_idx][self._edge_pos] = hhmm
        await self.hass.services.async_call(
            "text",
            "set_value",
            {
                "entity_id": self._windows_entity_id,
                "value": json.dumps(windows),
            },
            blocking=False,
        )


def _parse_hhmm(value: str) -> time | None:
    try:
        h, m = value.split(":")
        return time(int(h), int(m))
    except AttributeError, TypeError, ValueError:
        return None
