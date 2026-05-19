"""Schedule controller: ports the heating-schedule automation to Python."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CLIMATE_ENTITY,
    CONF_NAME,
    CONF_ROOMS,
    CONF_SETBACK,
    CONF_SLUG,
    DEFAULT_COMFORT,
    DEFAULT_SETBACK,
    DOMAIN,
    PAUSE_SETTLE_SECONDS,
    PAUSE_UNIQUE_SUFFIX,
)

if TYPE_CHECKING:
    from . import HeatingScheduleConfigEntry

_LOGGER = logging.getLogger(__name__)

_UNUSABLE_STATES = ("unavailable", "unknown", "none", "")


@dataclass
class _Room:
    slug: str
    name: str
    climate_entity: str
    windows_entity: str
    comfort_entity: str


class HeatingScheduleController:
    """Owns the schedule loop for one config entry."""

    def __init__(
        self, hass: HomeAssistant, entry: HeatingScheduleConfigEntry
    ) -> None:
        self.hass = hass
        self.entry = entry
        self._unsub_callbacks: list[CALLBACK_TYPE] = []
        self._rooms = self._resolve_rooms()
        self._pause_entity: str | None = self._resolve_pause_switch()
        self._setback: float = float(entry.data.get(CONF_SETBACK, DEFAULT_SETBACK))

    def _resolve_pause_switch(self) -> str | None:
        """Look up the integration's own pause switch via the registry."""
        registry = er.async_get(self.hass)
        return registry.async_get_entity_id(
            "switch", DOMAIN, f"{self.entry.entry_id}_{PAUSE_UNIQUE_SUFFIX}"
        )

    def _resolve_rooms(self) -> list[_Room]:
        """Resolve the actual entity_id for each per-room text/number.

        The suggested_object_id we set on the entity is just a hint; HA may
        append a suffix if there's a collision. We look up the real entity_id
        via the registry using the unique_id we set in text.py / number.py.
        """
        registry = er.async_get(self.hass)
        rooms: list[_Room] = []
        for room in self.entry.data.get(CONF_ROOMS, []):
            slug = room[CONF_SLUG]
            windows_eid = registry.async_get_entity_id(
                "text", DOMAIN, f"{self.entry.entry_id}_{slug}_windows"
            )
            comfort_eid = registry.async_get_entity_id(
                "number", DOMAIN, f"{self.entry.entry_id}_{slug}_comfort"
            )
            rooms.append(
                _Room(
                    slug=slug,
                    name=room[CONF_NAME],
                    climate_entity=room[CONF_CLIMATE_ENTITY],
                    windows_entity=windows_eid
                    or f"text.heating_schedule_windows_{slug}",
                    comfort_entity=comfort_eid
                    or f"number.heating_schedule_comfort_{slug}",
                )
            )
        return rooms

    # ── lifecycle ──────────────────────────────────────────────────────────

    async def async_start(self) -> None:
        """Wire up triggers and run an initial evaluation."""
        # Re-resolve in case platform setup just registered entities that
        # weren't yet in the registry when __init__ ran.
        self._rooms = self._resolve_rooms()
        self._pause_entity = self._resolve_pause_switch()
        watched_per_room: list[str] = []
        for room in self._rooms:
            watched_per_room.append(room.windows_entity)
            watched_per_room.append(room.comfort_entity)

        self._unsub_callbacks.append(
            async_track_state_change_event(
                self.hass, watched_per_room, self._on_room_entity_change
            )
        )

        if self._pause_entity:
            self._unsub_callbacks.append(
                async_track_state_change_event(
                    self.hass, [self._pause_entity], self._on_pause_change
                )
            )

        self._unsub_callbacks.append(
            async_track_time_interval(
                self.hass, self._on_tick, timedelta(minutes=1)
            )
        )

        self._unsub_callbacks.append(
            self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, self._on_ha_started
            )
        )

        if self.hass.is_running:
            self.hass.async_create_task(self._evaluate_all_after_settle())
        else:
            # HA still booting; the EVENT_HOMEASSISTANT_STARTED handler will fire.
            pass

    async def async_stop(self) -> None:
        """Cancel all subscriptions."""
        for unsub in self._unsub_callbacks:
            unsub()
        self._unsub_callbacks.clear()

    # ── triggers ──────────────────────────────────────────────────────────

    @callback
    def _on_tick(self, _now: datetime) -> None:
        self.hass.async_create_task(self._evaluate_all())

    @callback
    def _on_room_entity_change(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        for room in self._rooms:
            if entity_id in (room.windows_entity, room.comfort_entity):
                self.hass.async_create_task(self._evaluate_room(room))
                return

    @callback
    def _on_pause_change(self, event: Event[EventStateChangedData]) -> None:
        old = event.data.get("old_state")
        new = event.data.get("new_state")
        if old is None or new is None:
            return
        if old.state == "off" and new.state == "on":
            # Active push to setback so currently-warm rooms cool down,
            # mirroring the YAML "Apply Heating Pause" automation.
            self.hass.async_create_task(self._apply_setback_all())
        elif old.state == "on" and new.state == "off":
            # 5 s settle then re-evaluate from schedule + comfort.
            self.hass.async_create_task(self._evaluate_all_after_settle())

    @callback
    def _on_ha_started(self, _event: Event) -> None:
        self.hass.async_create_task(self._evaluate_all_after_settle())

    # ── evaluation ────────────────────────────────────────────────────────

    async def _evaluate_all_after_settle(self) -> None:
        """Wait PAUSE_SETTLE_SECONDS, then evaluate every room.

        Mirrors the 5-second delay in the YAML automation. It lets the
        Resume Heating scene restore land before the schedule re-asserts.
        """
        await asyncio.sleep(PAUSE_SETTLE_SECONDS)
        await self._evaluate_all()

    async def _evaluate_all(self) -> None:
        if self._is_paused():
            return
        await asyncio.gather(
            *(self._evaluate_room(room) for room in self._rooms),
            return_exceptions=False,
        )

    async def _apply_setback_all(self) -> None:
        """Push every room's climate entity to the setback temperature.

        Used when the pause switch flips on. Honors the same idempotent
        guard as the normal evaluation path so rooms already at setback
        stay quiet.
        """
        await asyncio.gather(
            *(self._write_climate(room, self._setback) for room in self._rooms),
            return_exceptions=False,
        )

    async def _write_climate(self, room: _Room, desired: float) -> None:
        climate_state = self.hass.states.get(room.climate_entity)
        if climate_state is None or climate_state.state in _UNUSABLE_STATES:
            return
        current = climate_state.attributes.get("temperature")
        if current is None:
            return
        try:
            if abs(float(current) - desired) < 1e-6:
                return
        except (TypeError, ValueError):
            return
        _LOGGER.debug(
            "heating_schedule: %s -> %.1f (pause-driven)",
            room.climate_entity,
            desired,
        )
        await self.hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": room.climate_entity, "temperature": desired},
            blocking=False,
        )

    async def _evaluate_room(self, room: _Room) -> None:
        if self._is_paused():
            return

        comfort = self._read_number(room.comfort_entity, DEFAULT_COMFORT)
        windows = self._read_windows(room.windows_entity)
        # dt_util.now() honours the HA-configured timezone; datetime.now()
        # in a Dockerised HA install would return the container's TZ.
        now = dt_util.now()
        minute = now.hour * 60 + now.minute
        active = any(_in_window(s, e, minute) for s, e in windows)
        desired = comfort if active else self._setback
        await self._write_climate(room, desired)

    # ── helpers ───────────────────────────────────────────────────────────

    def _is_paused(self) -> bool:
        if not self._pause_entity:
            return False
        state = self.hass.states.get(self._pause_entity)
        return state is not None and state.state == "on"

    def _read_number(self, entity_id: str, fallback: float) -> float:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in _UNUSABLE_STATES:
            return fallback
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return fallback

    def _read_windows(self, entity_id: str) -> list[tuple[int, int]]:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in _UNUSABLE_STATES:
            return []
        try:
            parsed = json.loads(state.state)
        except (TypeError, ValueError):
            return []
        if not isinstance(parsed, list):
            return []
        out: list[tuple[int, int]] = []
        for item in parsed:
            if not (isinstance(item, list) and len(item) == 2):
                continue
            try:
                s = _hhmm_to_min(item[0])
                e = _hhmm_to_min(item[1])
            except (TypeError, ValueError):
                continue
            out.append((s, e))
        return out


def _hhmm_to_min(value: object) -> int:
    if not isinstance(value, str):
        raise TypeError("expected HH:MM string")
    h, _, m = value.partition(":")
    return int(h) * 60 + int(m)


def _in_window(start: int, end: int, now: int) -> bool:
    """Wrap-aware window membership matching the YAML/card semantics."""
    if start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end
