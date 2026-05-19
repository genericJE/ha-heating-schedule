"""Shared window-list helpers used by the config flow, number entity, and time entities.

Mirrors the JS placeNewWindow / resizeWindows logic in the card so that
adding or removing windows from any surface (wizard slider, device-page
number entity, card editor) produces the same non-overlapping defaults.
"""

from __future__ import annotations

import json
from typing import Iterable

from .const import MAX_WINDOWS

DAY = 1440
NEW_WINDOW_MIN_MINUTES = 60
DEFAULT_WINDOW: list[str] = ["07:00", "22:00"]


def hhmm_to_min(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def min_to_hhmm(value: int) -> str:
    v = value % DAY
    return f"{v // 60:02d}:{v % 60:02d}"


def parse_windows(raw: str | None) -> list[list[str]]:
    """Return the JSON-encoded window list, filtered to valid [start, end] pairs."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    out: list[list[str]] = []
    for item in parsed:
        if isinstance(item, list) and len(item) == 2 and all(isinstance(x, str) for x in item):
            out.append([item[0], item[1]])
    return out


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
    if len(out) == clamped:
        return out
    if len(out) > clamped:
        return out[:clamped]
    while len(out) < clamped:
        out.append(place_new_window(out))
    return out


def initial_windows_json(count: int, base: tuple[str, str]) -> str:
    """Wizard helper: build a starting JSON of size `count` from a single base window."""
    out = [list(base)]
    while len(out) < count:
        out.append(place_new_window(out))
    return json.dumps(out[: max(1, min(MAX_WINDOWS, int(count)))])
