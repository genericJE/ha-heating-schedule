"""Config flow for Heating Schedule.

First-time setup walks the user through:
  1. user     - how many rooms (1..N)
  2. room     - looped once per room: name + climate + optional sensors + comfort + windows
  3. globals  - optional pause boolean + setback temperature
  4. summary  - shows the pasteable dashboard YAML, finishing creates the entry

When an entry already exists, the "Add entry" button reuses the same flow
but skips straight to `async_step_add_room` — a one-shot variant of the
per-room step that appends to the existing entry and reloads it.

The walked state lives in self._draft until the final step calls
async_create_entry (first run) or async_update_entry (add-room run).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.util import slugify

from ._windows import initial_windows_json
from .const import (
    CONF_CLIMATE_ENTITY,
    CONF_COMFORT_DEFAULT,
    CONF_CURRENT_TEMP_ENTITY,
    CONF_NAME,
    CONF_ROOMS,
    CONF_SETBACK,
    CONF_SLUG,
    CONF_WINDOW_ENTITY,
    CONF_WINDOWS_DEFAULT,
    DEFAULT_COMFORT,
    DEFAULT_COMFORT_MAX,
    DEFAULT_COMFORT_MIN,
    DEFAULT_COMFORT_STEP,
    DEFAULT_SETBACK,
    DOMAIN,
    MAX_WINDOWS,
)

# Per-room defaults for the first window. The wizard's window-count slider
# generates additional windows from there via initial_windows_json.
_SUGGESTED_ROOMS: tuple[tuple[str, tuple[str, str]], ...] = (
    ("Bedroom", ("22:00", "07:00")),
    ("Living Room", ("07:00", "23:00")),
    ("Kitchen", ("07:00", "22:00")),
    ("Bathroom", ("07:00", "22:00")),
)
_MAX_ROOMS = 12

CONF_ROOM_COUNT = "room_count"
CONF_WINDOW_COUNT = "window_count"


def _room_schema(suggested_name: str) -> vol.Schema:
    """Schema shared by the per-room and add-room steps."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=suggested_name): str,
            vol.Required(CONF_CLIMATE_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="climate")
            ),
            vol.Optional(CONF_CURRENT_TEMP_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(CONF_WINDOW_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            vol.Required(CONF_COMFORT_DEFAULT, default=DEFAULT_COMFORT): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=DEFAULT_COMFORT_MIN,
                    max=DEFAULT_COMFORT_MAX,
                    step=DEFAULT_COMFORT_STEP,
                    unit_of_measurement="°C",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(CONF_WINDOW_COUNT, default=1): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=MAX_WINDOWS,
                    step=1,
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
        }
    )


def _room_payload(
    user_input: Mapping[str, Any],
    slug: str,
    suggested_base: tuple[str, str],
) -> dict[str, Any]:
    """Build the per-room dict stored in entry.data from a step submission."""
    count = int(user_input.get(CONF_WINDOW_COUNT, 1))
    return {
        CONF_SLUG: slug,
        CONF_NAME: user_input[CONF_NAME].strip(),
        CONF_CLIMATE_ENTITY: user_input[CONF_CLIMATE_ENTITY],
        CONF_CURRENT_TEMP_ENTITY: user_input.get(CONF_CURRENT_TEMP_ENTITY) or None,
        CONF_WINDOW_ENTITY: user_input.get(CONF_WINDOW_ENTITY) or None,
        CONF_COMFORT_DEFAULT: float(user_input[CONF_COMFORT_DEFAULT]),
        CONF_WINDOWS_DEFAULT: initial_windows_json(count, suggested_base),
    }


class HeatingScheduleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Heating Schedule."""

    VERSION = 1

    def __init__(self) -> None:
        self._draft: dict[str, Any] = {
            CONF_ROOMS: [],
            CONF_SETBACK: DEFAULT_SETBACK,
        }
        self._room_count: int = 0
        self._current_room_index: int = 0

    # ── step 1: how many rooms ────────────────────────────────────────────

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        # "Add entry" on an integration that already has an entry should add
        # one room to that entry, not start a parallel multi-room setup.
        if self._async_current_entries():
            return await self.async_step_add_room()

        if user_input is not None:
            self._room_count = int(user_input[CONF_ROOM_COUNT])
            self._current_room_index = 0
            return await self.async_step_room()

        schema = vol.Schema(
            {
                vol.Required(CONF_ROOM_COUNT, default=4): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=_MAX_ROOMS,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    # ── step 2: per-room identity + entities ──────────────────────────────

    async def async_step_room(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        suggested_name, suggested_base = _SUGGESTED_ROOMS[
            self._current_room_index % len(_SUGGESTED_ROOMS)
        ]

        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors[CONF_NAME] = "name_required"
            else:
                slug = _unique_slug(name, [r[CONF_SLUG] for r in self._draft[CONF_ROOMS]])
                self._draft[CONF_ROOMS].append(_room_payload(user_input, slug, suggested_base))
                self._current_room_index += 1
                if self._current_room_index >= self._room_count:
                    return await self.async_step_globals()
                return await self.async_step_room()

        return self.async_show_form(
            step_id="room",
            data_schema=_room_schema(suggested_name),
            errors=errors,
            description_placeholders={
                "index": str(self._current_room_index + 1),
                "total": str(self._room_count),
            },
        )

    # ── step 3: pause boolean + setback ──────────────────────────────────

    async def async_step_globals(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._draft[CONF_SETBACK] = float(user_input.get(CONF_SETBACK, DEFAULT_SETBACK))
            return await self.async_step_summary()

        schema = vol.Schema(
            {
                vol.Required(CONF_SETBACK, default=DEFAULT_SETBACK): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=DEFAULT_COMFORT_MIN,
                        max=DEFAULT_COMFORT_MAX,
                        step=DEFAULT_COMFORT_STEP,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="globals", data_schema=schema)

    # ── step 4: pasteable dashboard YAML, then create the entry ──────────

    async def async_step_summary(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="Heating Schedule",
                data=self._draft,
            )

        return self.async_show_form(
            step_id="summary",
            data_schema=vol.Schema({}),
            description_placeholders={
                "dashboard_yaml": _dashboard_snippet(self._draft[CONF_ROOMS]),
            },
        )

    # ── add-room: append a single room to an existing entry ──────────────

    async def async_step_add_room(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._async_current_entries()[0]
        existing_rooms: list[Mapping[str, Any]] = entry.data.get(CONF_ROOMS, [])
        taken_slugs = [r[CONF_SLUG] for r in existing_rooms]
        suggested_name, suggested_base = _suggest_unused_room(taken_slugs)

        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors[CONF_NAME] = "name_required"
            else:
                slug = _unique_slug(name, taken_slugs)
                new_room = _room_payload(user_input, slug, suggested_base)
                new_data = dict(entry.data)
                new_data[CONF_ROOMS] = [*existing_rooms, new_room]
                self.hass.config_entries.async_update_entry(entry, data=new_data)
                # async_update_entry fires the update listener wired in
                # __init__.py, which reloads the entry — that's what spins up
                # the new room's entities. Aborting here is the standard
                # "extend an existing entry" pattern.
                return self.async_abort(reason="room_added")

        return self.async_show_form(
            step_id="add_room",
            data_schema=_room_schema(suggested_name),
            errors=errors,
            description_placeholders={
                "existing_count": str(len(existing_rooms)),
            },
        )


# ── helpers ────────────────────────────────────────────────────────────────


def _suggest_unused_room(taken: list[str]) -> tuple[str, tuple[str, str]]:
    """Pick the first suggested room whose slug isn't already taken.

    Falls back to the first suggestion if every preset name is already
    in use — the user can rename it before submitting.
    """
    for name, base in _SUGGESTED_ROOMS:
        if slugify(name) not in taken:
            return name, base
    return _SUGGESTED_ROOMS[0]


def _unique_slug(name: str, taken: list[str]) -> str:
    base = slugify(name) or "room"
    if base not in taken:
        return base
    i = 2
    while f"{base}_{i}" in taken:
        i += 1
    return f"{base}_{i}"


def _dashboard_snippet(rooms: list[Mapping[str, Any]]) -> str:
    """Build a pasteable Lovelace YAML block for the configured rooms.

    Entity IDs follow HA's default for has_entity_name=True devices:
    {domain}.{device_slug}_{translation_key}, where device_slug is the
    slugified room name.
    """
    lines: list[str] = [
        "type: grid",
        "column_span: 2",
        "cards:",
        "  - type: heading",
        "    heading: Schedule",
        "    icon: mdi:calendar-clock",
        "    heading_style: title",
    ]
    for room in rooms:
        slug = room[CONF_SLUG]
        lines.append("  - type: custom:heating-window-slider-card")
        lines.append(f"    name: {room[CONF_NAME]}")
        lines.append(f"    windows_entity: text.{slug}_windows")
        lines.append(f"    comfort_entity: number.{slug}_comfort")
        lines.append(f"    climate_entity: {room[CONF_CLIMATE_ENTITY]}")
        if room.get(CONF_CURRENT_TEMP_ENTITY):
            lines.append(f"    current_temp_entity: {room[CONF_CURRENT_TEMP_ENTITY]}")
        if room.get(CONF_WINDOW_ENTITY):
            lines.append(f"    window_entity: {room[CONF_WINDOW_ENTITY]}")
        lines.append("    grid_options:")
        lines.append("      columns: 12")
        lines.append("      rows: auto")
    return "\n".join(lines)
