"""Config flow for Heating Schedule.

Walks the user through:
  1. user     - how many rooms (1..N)
  2. room     - looped once per room: name + climate + optional sensors + comfort + windows
  3. globals  - optional pause boolean + setback temperature
  4. summary  - shows the pasteable dashboard YAML, finishing creates the entry

The walked state lives in self._draft until the final step calls
async_create_entry.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.util import slugify

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
    DEFAULT_WINDOWS_JSON,
    DOMAIN,
    MAX_WINDOWS,
)

_LOGGER = logging.getLogger(__name__)

# Per-room defaults for the first window. The wizard's window-count slider
# generates additional windows from there using _place_new_window.
_SUGGESTED_ROOMS: tuple[tuple[str, tuple[str, str]], ...] = (
    ("Bedroom", ("22:00", "07:00")),
    ("Living Room", ("07:00", "23:00")),
    ("Kitchen", ("07:00", "22:00")),
    ("Bathroom", ("07:00", "22:00")),
)
_MAX_ROOMS = 12
_DAY = 1440
_NEW_WINDOW_MIN_MINUTES = 60

CONF_ROOM_COUNT = "room_count"
CONF_WINDOW_COUNT = "window_count"


def _hhmm_to_min(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _min_to_hhmm(m: int) -> str:
    v = m % _DAY
    return f"{v // 60:02d}:{v % 60:02d}"


def _place_new_window(existing: list[list[str]]) -> list[str]:
    """Python port of placeNewWindow in heating-window-slider-card.js.

    Picks a new [start, end] window centred in the largest cyclic gap
    between the existing ones, so additions don't stack on the same slot.
    """
    if not existing:
        return ["07:00", "22:00"]
    spans: list[tuple[int, int]] = []
    for w in existing:
        s, e = _hhmm_to_min(w[0]), _hhmm_to_min(w[1])
        if s == e:
            continue
        if s < e:
            spans.append((s, e))
        else:
            spans.append((s, _DAY))
            spans.append((0, e))
    spans.sort()
    if not spans:
        return ["07:00", "22:00"]
    best_gap_start, best_gap_size = 0, 0
    for i, span in enumerate(spans):
        prev = (spans[-1][0] - _DAY, spans[-1][1] - _DAY) if i == 0 else spans[i - 1]
        gap_start, gap_size = prev[1], span[0] - prev[1]
        if gap_size > best_gap_size:
            best_gap_size = gap_size
            best_gap_start = gap_start % _DAY
    if best_gap_size < _NEW_WINDOW_MIN_MINUTES:
        best_gap_size = max(best_gap_size, 30)
    win_size = min(_NEW_WINDOW_MIN_MINUTES, best_gap_size // 2)
    start = (best_gap_start + (best_gap_size - win_size) // 2 + _DAY) % _DAY
    end = (start + win_size) % _DAY
    return [_min_to_hhmm(start), _min_to_hhmm(end)]


def _generate_initial_windows(count: int, base: tuple[str, str]) -> str:
    """Build the JSON used as the text entity's first state, given count."""
    count = max(1, min(MAX_WINDOWS, int(count)))
    windows = [list(base)]
    while len(windows) < count:
        windows.append(_place_new_window(windows))
    return json.dumps(windows)


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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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

    async def async_step_room(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        suggested_name, suggested_base = _SUGGESTED_ROOMS[
            self._current_room_index % len(_SUGGESTED_ROOMS)
        ]

        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors[CONF_NAME] = "name_required"
            else:
                slug = _unique_slug(
                    name, [r[CONF_SLUG] for r in self._draft[CONF_ROOMS]]
                )
                count = int(user_input.get(CONF_WINDOW_COUNT, 1))
                self._draft[CONF_ROOMS].append(
                    {
                        CONF_SLUG: slug,
                        CONF_NAME: name,
                        CONF_CLIMATE_ENTITY: user_input[CONF_CLIMATE_ENTITY],
                        CONF_CURRENT_TEMP_ENTITY: user_input.get(
                            CONF_CURRENT_TEMP_ENTITY
                        )
                        or None,
                        CONF_WINDOW_ENTITY: user_input.get(CONF_WINDOW_ENTITY)
                        or None,
                        CONF_COMFORT_DEFAULT: float(
                            user_input[CONF_COMFORT_DEFAULT]
                        ),
                        CONF_WINDOWS_DEFAULT: _generate_initial_windows(
                            count, suggested_base
                        ),
                    }
                )
                self._current_room_index += 1
                if self._current_room_index >= self._room_count:
                    return await self.async_step_globals()
                return await self.async_step_room()

        schema = vol.Schema(
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
                vol.Required(
                    CONF_COMFORT_DEFAULT, default=DEFAULT_COMFORT
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=DEFAULT_COMFORT_MIN,
                        max=DEFAULT_COMFORT_MAX,
                        step=DEFAULT_COMFORT_STEP,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_WINDOW_COUNT, default=1
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=MAX_WINDOWS,
                        step=1,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="room",
            data_schema=schema,
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
            self._draft[CONF_SETBACK] = float(
                user_input.get(CONF_SETBACK, DEFAULT_SETBACK)
            )
            return await self.async_step_summary()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SETBACK, default=DEFAULT_SETBACK
                ): selector.NumberSelector(
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


# ── helpers ────────────────────────────────────────────────────────────────


def _unique_slug(name: str, taken: list[str]) -> str:
    base = slugify(name) or "room"
    if base not in taken:
        return base
    i = 2
    while f"{base}_{i}" in taken:
        i += 1
    return f"{base}_{i}"


def _validated_windows(raw: str) -> str:
    """Return the canonical JSON form of raw windows, or the default."""
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return DEFAULT_WINDOWS_JSON
    if not isinstance(parsed, list) or not parsed:
        return DEFAULT_WINDOWS_JSON
    cleaned: list[list[str]] = []
    for item in parsed:
        if not (
            isinstance(item, list) and len(item) == 2 and all(_is_hhmm(x) for x in item)
        ):
            return DEFAULT_WINDOWS_JSON
        cleaned.append(list(item))
    return json.dumps(cleaned)


def _is_hhmm(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        return False
    try:
        h = int(value[:2])
        m = int(value[3:])
    except ValueError:
        return False
    return 0 <= h <= 23 and 0 <= m <= 59


def _dashboard_snippet(rooms: list[Mapping[str, Any]]) -> str:
    """Build a pasteable Lovelace YAML block for the configured rooms.

    Entity IDs follow HA's default for has_entity_name=True devices:
    {domain}.{device_slug}_{translation_key}, where device_slug is the
    slugified room name.
    """
    lines: list[str] = ["type: grid", "column_span: 2", "cards:"]
    lines.append("  - type: heading")
    lines.append("    heading: Schedule")
    lines.append("    icon: mdi:calendar-clock")
    lines.append("    heading_style: title")
    for room in rooms:
        slug = room[CONF_SLUG]
        lines.append("  - type: custom:heating-window-slider-card")
        lines.append(f"    name: {room[CONF_NAME]}")
        lines.append(f"    windows_entity: text.{slug}_windows")
        lines.append(f"    comfort_entity: number.{slug}_comfort")
        lines.append(f"    climate_entity: {room[CONF_CLIMATE_ENTITY]}")
        if room.get(CONF_CURRENT_TEMP_ENTITY):
            lines.append(
                f"    current_temp_entity: {room[CONF_CURRENT_TEMP_ENTITY]}"
            )
        if room.get(CONF_WINDOW_ENTITY):
            lines.append(f"    window_entity: {room[CONF_WINDOW_ENTITY]}")
        lines.append("    grid_options:")
        lines.append("      columns: 12")
        lines.append("      rows: auto")
    return "\n".join(lines)
