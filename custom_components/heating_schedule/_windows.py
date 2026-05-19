"""Shared window-list helpers used by the config flow, number entity, and time entities.

Mirrors the JS placeNewWindow / resizeWindows logic in the card so that
adding or removing windows from any surface (wizard slider, device-page
number entity, card editor) produces the same non-overlapping defaults.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from .const import MAX_WINDOWS

DAY = 1440
NEW_WINDOW_MIN_MINUTES = 60
DEFAULT_WINDOW: list[str] = ["07:00", "22:00"]

# States that mean "no usable value". Centralised so every reader matches
# what HA actually emits (STATE_NONE is "none"; empty string is the rare
# pre-restore window).
UNUSABLE_STATES: frozenset[str] = frozenset(
    {STATE_UNAVAILABLE, STATE_UNKNOWN, "none", ""}
)


def is_unusable(state: str | None) -> bool:
    return state is None or state in UNUSABLE_STATES


def hhmm_to_min(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def min_to_hhmm(value: int) -> str:
    v = value % DAY
    return f"{v // 60:02d}:{v % 60:02d}"


def is_hhmm(value: object) -> bool:
    """Strict HH:MM validation: 5 chars, colon at index 2, hour 0-23, minute 0-59."""
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        return False
    try:
        h = int(value[:2])
        m = int(value[3:])
    except ValueError:
        return False
    return 0 <= h <= 23 and 0 <= m <= 59


def parse_windows(raw: str | None) -> list[list[str]]:
    """Return the JSON-encoded window list, filtered to valid [start, end] pairs.

    Each entry is two HH:MM-shaped strings. Format-invalid entries are dropped.
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [
        [item[0], item[1]]
        for item in parsed
        if isinstance(item, list)
        and len(item) == 2
        and is_hhmm(item[0])
        and is_hhmm(item[1])
    ]


def parse_windows_minutes(raw: str | None) -> list[tuple[int, int]]:
    """parse_windows but with each edge converted to minutes-since-midnight."""
    return [(hhmm_to_min(s), hhmm_to_min(e)) for s, e in parse_windows(raw)]


def place_new_window(existing: Iterable[Iterable[str]]) -> list[str]:
    """Pick a new window centred in the largest cyclic gap between existing ones."""
    pairs = [list(e) for e in existing]
    if not pairs:
        return list(DEFAULT_WINDOW)
    spans: list[tuple[int, int]] = []
    for w in pairs:
        s, e = hhmm_to_min(w[0]), hhmm_to_min(w[1])
        if s == e:
            continue
        if s < e:
            spans.append((s, e))
        else:
            spans.append((s, DAY))
            spans.append((0, e))
    spans.sort()
    if not spans:
        return list(DEFAULT_WINDOW)
    best_gap_start, best_gap_size = 0, 0
    for i, span in enumerate(spans):
        prev = (spans[-1][0] - DAY, spans[-1][1] - DAY) if i == 0 else spans[i - 1]
        gap_start, gap_size = prev[1], span[0] - prev[1]
        if gap_size > best_gap_size:
            best_gap_size = gap_size
            best_gap_start = gap_start % DAY
    if best_gap_size < NEW_WINDOW_MIN_MINUTES:
        best_gap_size = max(best_gap_size, 30)
    win_size = min(NEW_WINDOW_MIN_MINUTES, best_gap_size // 2)
    start = (best_gap_start + (best_gap_size - win_size) // 2 + DAY) % DAY
    end = (start + win_size) % DAY
    return [min_to_hhmm(start), min_to_hhmm(end)]


def resize_windows(existing: Iterable[Iterable[str]], target: int) -> list[list[str]]:
    """Truncate or grow `existing` to exactly `target` windows."""
    clamped = max(1, min(MAX_WINDOWS, int(target)))
    out = [list(w) for w in existing if isinstance(w, list) and len(w) == 2]
    if len(out) > clamped:
        return out[:clamped]
    while len(out) < clamped:
        out.append(place_new_window(out))
    return out


def initial_windows_json(count: int, base: tuple[str, str]) -> str:
    """Wizard helper: build a starting JSON of size `count` from a single base window."""
    clamped = max(1, min(MAX_WINDOWS, int(count)))
    out: list[list[str]] = [list(base)]
    while len(out) < clamped:
        out.append(place_new_window(out))
    return json.dumps(out[:clamped])


def validated_windows_json(raw: str, default: str) -> str:
    """Return raw if it parses to a non-empty, length-bounded windows list, else default."""
    windows = parse_windows(raw)
    if not windows or len(windows) > MAX_WINDOWS:
        return default
    return json.dumps(windows)
