"""Schedule controller: ports the heating-schedule automation to Python."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.const import (
    EVENT_HOMEASSISTANT_STARTED,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Context,
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

from ._windows import is_unusable, parse_windows_minutes
from .const import (
    CONF_CLIMATE_ENTITY,
    CONF_NAME,
    CONF_ROOMS,
    CONF_SETBACK,
    CONF_SLUG,
    DEFAULT_COMFORT,
    DEFAULT_SETBACK,
    DOMAIN,
    EXTERNAL_PAUSE_BOOLEAN,
    MAX_WINDOWS,
    PAUSE_SETTLE_SECONDS,
    PAUSE_SNAPSHOT_DELAY_SECONDS,
    PAUSE_UNIQUE_SUFFIX,
    SETBACK_UNIQUE_SUFFIX,
)

if TYPE_CHECKING:
    from . import HeatingScheduleConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass
class _Room:
    slug: str
    name: str
    climate_entity: str
    windows_entity: str
    comfort_entity: str


def _in_window(start: int, end: int, now: int) -> bool:
    """Wrap-aware window membership matching the YAML/card semantics."""
    if start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end


class HeatingScheduleController:
    """Owns the schedule loop for one config entry."""

    def __init__(
        self, hass: HomeAssistant, entry: HeatingScheduleConfigEntry
    ) -> None:
        self.hass = hass
        self.entry = entry
        self._unsub_callbacks: list[CALLBACK_TYPE] = []
        # _rooms + _pause_entity are resolved in async_start, after platform
        # setup has populated the entity registry. Resolving here would race
        # against the platform forward and yield empty results.
        self._rooms: list[_Room] = []
        self._pause_entity: str | None = None
        self._setback_entity: str | None = None
        self._pause_sync = _PauseSync(hass)

    def _resolve_pause_switch(self) -> str | None:
        """Look up the integration's own pause switch via the registry."""
        registry = er.async_get(self.hass)
        return registry.async_get_entity_id(
            "switch", DOMAIN, f"{self.entry.entry_id}_{PAUSE_UNIQUE_SUFFIX}"
        )

    def _resolve_setback_number(self) -> str | None:
        """Look up the integration's setback number entity via the registry."""
        registry = er.async_get(self.hass)
        return registry.async_get_entity_id(
            "number", DOMAIN, f"{self.entry.entry_id}_{SETBACK_UNIQUE_SUFFIX}"
        )

    def _resolve_rooms(self) -> list[_Room]:
        """Resolve the actual entity_id for each per-room text/number.

        The suggested_object_id we set on the entity is just a hint; HA may
        append a suffix if there's a collision. We look up the real entity_id
        via the registry using the unique_id we set in text.py / number.py.
        Falls back to the suggested form when the registry lookup misses,
        which keeps the controller running even if a room's entity has been
        manually removed from the registry.
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
                    windows_entity=windows_eid or f"text.{slug}_windows",
                    comfort_entity=comfort_eid or f"number.{slug}_comfort",
                )
            )
        return rooms

    # ── lifecycle ──────────────────────────────────────────────────────────

    async def async_start(self) -> None:
        """Wire up triggers and run an initial evaluation."""
        self._rooms = self._resolve_rooms()
        self._pause_entity = self._resolve_pause_switch()
        self._setback_entity = self._resolve_setback_number()

        watched_per_room = [
            entity
            for room in self._rooms
            for entity in (room.windows_entity, room.comfort_entity)
        ]
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

        if self._setback_entity:
            self._unsub_callbacks.append(
                async_track_state_change_event(
                    self.hass, [self._setback_entity], self._on_setback_change
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

        await self._pause_sync.async_start(self._pause_entity)

        # Initial reconciliation in case the user's previously-set count
        # differs from the registry's stored disabled_by state.
        for room in self._rooms:
            self._reconcile_time_entities_for_room(room)
        # One-shot migration: hide the raw windows text entity from the
        # device page on installs that pre-date the time-picker platform.
        # Only flips entities the integration owns; user-hidden ones are
        # left alone.
        self._hide_text_entities_on_first_run()

        if self.hass.is_running:
            self.hass.async_create_task(self._evaluate_all_after_settle())
        # else: HA still booting; EVENT_HOMEASSISTANT_STARTED handler will fire.

    async def async_stop(self) -> None:
        """Cancel all subscriptions."""
        await self._pause_sync.async_stop()
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
            if entity_id == room.windows_entity:
                self._reconcile_time_entities_for_room(room)
                self.hass.async_create_task(self._evaluate_room(room))
                return
            if entity_id == room.comfort_entity:
                self.hass.async_create_task(self._evaluate_room(room))
                return

    @callback
    def _hide_text_entities_on_first_run(self) -> None:
        registry = er.async_get(self.hass)
        for room in self._rooms:
            unique_id = f"{self.entry.entry_id}_{room.slug}_windows"
            entity_id = registry.async_get_entity_id("text", DOMAIN, unique_id)
            if not entity_id:
                continue
            entry = registry.async_get(entity_id)
            if entry is None:
                continue
            update: dict[str, Any] = {}
            # Detach from the room device — covers existing installs that
            # were created before HeatingWindowsText dropped device_info.
            if entry.device_id is not None:
                update["device_id"] = None
            # Mark hidden — covers existing installs that pre-date
            # entity_registry_visible_default=False. Skip if the user has
            # already chosen a hidden_by themselves (USER, etc).
            if entry.hidden_by is None:
                update["hidden_by"] = er.RegistryEntryHider.INTEGRATION
            if update:
                registry.async_update_entity(entity_id, **update)

    @callback
    def _reconcile_time_entities_for_room(self, room: _Room) -> None:
        """Match each per-edge time entity's disabled_by to the current count.

        The time platform pre-creates MAX_WINDOWS * 2 entities per room.
        Slots beyond the current window count are disabled_by=INTEGRATION so
        the device page only shows the entities the user actually has windows
        for. User-initiated disables (USER, CONFIG_ENTRY etc.) are left alone.
        """
        registry = er.async_get(self.hass)
        count = len(self._read_windows(room.windows_entity))
        for idx in range(MAX_WINDOWS):
            should_be_enabled = idx < count
            for edge in ("start", "end"):
                unique_id = f"{self.entry.entry_id}_{room.slug}_window_{idx + 1}_{edge}"
                entity_id = registry.async_get_entity_id("time", DOMAIN, unique_id)
                if not entity_id:
                    continue
                entry = registry.async_get(entity_id)
                if entry is None:
                    continue
                if (
                    should_be_enabled
                    and entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION
                ):
                    registry.async_update_entity(entity_id, disabled_by=None)
                elif not should_be_enabled and entry.disabled_by is None:
                    registry.async_update_entity(
                        entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
                    )

    @callback
    def _on_setback_change(self, _event: Event[EventStateChangedData]) -> None:
        # Re-evaluate every room so the new setback takes effect now rather
        # than waiting for the next per-minute tick.
        self.hass.async_create_task(self._evaluate_all())

    @callback
    def _on_pause_change(self, event: Event[EventStateChangedData]) -> None:
        old = event.data.get("old_state")
        new = event.data.get("new_state")
        if old is None or new is None:
            return
        if old.state == STATE_OFF and new.state == STATE_ON:
            # Brief delay then push setback so a peer automation snapshotting
            # the climates on the same boolean edge (Apply Heating Pause's
            # scene.create) captures pre-pause state before we lower it.
            self.hass.async_create_task(self._apply_setback_all_after_snapshot())
        elif old.state == STATE_ON and new.state == STATE_OFF:
            # 5s settle then re-evaluate from schedule + comfort.
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
            *(self._evaluate_room(room) for room in self._rooms)
        )

    async def _apply_setback_all_after_snapshot(self) -> None:
        """Let a peer automation snapshot pre-pause state, then push setback."""
        await asyncio.sleep(PAUSE_SNAPSHOT_DELAY_SECONDS)
        await self._apply_setback_all()

    async def _apply_setback_all(self) -> None:
        """Push every room's climate entity to the setback temperature.

        Used when the pause switch flips on. Honors the same idempotent
        guard as the normal evaluation path so rooms already at setback
        stay quiet.
        """
        setback = self._read_setback()
        await asyncio.gather(
            *(self._write_climate(room, setback) for room in self._rooms)
        )

    async def _write_climate(self, room: _Room, desired: float) -> None:
        climate_state = self.hass.states.get(room.climate_entity)
        if climate_state is None or is_unusable(climate_state.state):
            return
        # Respect a user-disabled climate. set_temperature on an off
        # entity is silently dropped on most platforms (BT included), so
        # the write would succeed but heat would never come on — leave
        # the schedule visibly inactive instead.
        if climate_state.state == STATE_OFF:
            return
        # Skip while Better Thermostat's window-open frost-protect is
        # active: BT holds its frost target for as long as the window is
        # open, so a write here loses every tick and just generates churn
        # until the window closes.
        if climate_state.attributes.get("window_open"):
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
            "heating_schedule: %s -> %.1f", room.climate_entity, desired
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
        desired = comfort if active else self._read_setback()
        await self._write_climate(room, desired)

    # ── helpers ───────────────────────────────────────────────────────────

    def _is_paused(self) -> bool:
        if not self._pause_entity:
            return False
        state = self.hass.states.get(self._pause_entity)
        return state is not None and state.state == STATE_ON

    def _read_setback(self) -> float:
        """Read the current setback from the hub number entity.

        Falls back to the wizard-stored value (and then DEFAULT_SETBACK) if
        the entity hasn't been resolved yet or its state is unavailable —
        which only happens during the brief window between platform forward
        and async_start, or if a user has manually removed the entity.
        """
        if self._setback_entity:
            state = self.hass.states.get(self._setback_entity)
            if state is not None and not is_unusable(state.state):
                try:
                    return float(state.state)
                except (TypeError, ValueError):
                    pass
        return float(self.entry.data.get(CONF_SETBACK, DEFAULT_SETBACK))

    def _read_number(self, entity_id: str, fallback: float) -> float:
        state = self.hass.states.get(entity_id)
        if state is None or is_unusable(state.state):
            return fallback
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return fallback

    def _read_windows(self, entity_id: str) -> list[tuple[int, int]]:
        state = self.hass.states.get(entity_id)
        if state is None or is_unusable(state.state):
            return []
        return parse_windows_minutes(state.state)


class _PauseSync:
    """Mirror switch.heating_schedule_pause <-> input_boolean.heating_paused.

    Either side can be toggled by anything (dashboard tile, YAML automation,
    voice assistant, leave-home notification). When one flips, we propagate
    to the other so the rest of the install (Apply Heating Pause, Resume
    Heating on Return, Hc1DayTemp lowering, scene snapshot, vacation cascade)
    keeps working unchanged. The integration's switch is the canonical pause
    state the controller responds to; the input_boolean is a peer the rest of
    the install was already wired to.

    Feedback-loop guard: every sync write uses a fresh Context. The peer's
    resulting state_changed event carries that context.id; we skip those.
    The peer only acts on changes that came from elsewhere.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._switch_entity: str | None = None
        self._own_context_ids: set[str] = set()
        self._unsubs: list[CALLBACK_TYPE] = []

    async def async_start(self, switch_entity: str | None) -> None:
        if not switch_entity:
            return
        self._switch_entity = switch_entity
        self._unsubs.append(
            async_track_state_change_event(
                self.hass, [switch_entity], self._on_switch_change
            )
        )
        self._unsubs.append(
            async_track_state_change_event(
                self.hass, [EXTERNAL_PAUSE_BOOLEAN], self._on_boolean_change
            )
        )
        # Initial alignment: if the boolean exists and disagrees with the
        # switch, push the boolean's state onto the switch. The boolean has
        # been the canonical pause source until now, so on first install we
        # adopt whatever state it's already in.
        bool_state = self.hass.states.get(EXTERNAL_PAUSE_BOOLEAN)
        sw_state = self.hass.states.get(switch_entity)
        if (
            bool_state
            and bool_state.state in (STATE_ON, STATE_OFF)
            and sw_state
            and sw_state.state != bool_state.state
        ):
            await self._mirror_to_switch(bool_state.state)

    async def async_stop(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs.clear()
        self._own_context_ids.clear()

    @callback
    def _on_switch_change(self, event: Event[EventStateChangedData]) -> None:
        if event.context.id in self._own_context_ids:
            self._own_context_ids.discard(event.context.id)
            return
        new_state = _propagatable_new_state(event)
        if new_state is None or not self.hass.states.get(EXTERNAL_PAUSE_BOOLEAN):
            return
        self.hass.async_create_task(self._mirror_to_boolean(new_state))

    @callback
    def _on_boolean_change(self, event: Event[EventStateChangedData]) -> None:
        if event.context.id in self._own_context_ids:
            self._own_context_ids.discard(event.context.id)
            return
        new_state = _propagatable_new_state(event)
        if (
            new_state is None
            or not self._switch_entity
            or not self.hass.states.get(self._switch_entity)
        ):
            return
        self.hass.async_create_task(self._mirror_to_switch(new_state))

    async def _mirror_to_switch(self, state: str) -> None:
        # Skip the service call if the target is already at the desired
        # state. Without this, a same-state turn_on/turn_off would no-op
        # silently and leak the context id (no state-change event to
        # discard it).
        if not self._switch_entity:
            return
        cur = self.hass.states.get(self._switch_entity)
        if cur is None or cur.state == state:
            return
        ctx = Context()
        self._own_context_ids.add(ctx.id)
        await self.hass.services.async_call(
            "switch",
            "turn_on" if state == STATE_ON else "turn_off",
            {"entity_id": self._switch_entity},
            blocking=False,
            context=ctx,
        )

    async def _mirror_to_boolean(self, state: str) -> None:
        cur = self.hass.states.get(EXTERNAL_PAUSE_BOOLEAN)
        if cur is None or cur.state == state:
            return
        ctx = Context()
        self._own_context_ids.add(ctx.id)
        await self.hass.services.async_call(
            "input_boolean",
            "turn_on" if state == STATE_ON else "turn_off",
            {"entity_id": EXTERNAL_PAUSE_BOOLEAN},
            blocking=False,
            context=ctx,
        )


def _propagatable_new_state(event: Event[EventStateChangedData]) -> str | None:
    """Return the new state if this change should be propagated, else None.

    Both old and new state must be on/off. A transition out of unavailable/
    unknown (e.g. unavailable -> off when the integration reloads while a
    pause is active) is the entity re-materialising at its restored default,
    not a user toggle, and propagating it would silently clear the peer.
    """
    old = event.data.get("old_state")
    new = event.data.get("new_state")
    if (
        new is None
        or old is None
        or new.state == old.state
        or new.state not in (STATE_ON, STATE_OFF)
        or old.state not in (STATE_ON, STATE_OFF)
    ):
        return None
    return new.state
