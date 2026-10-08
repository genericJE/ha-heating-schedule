"""Heating Schedule integration."""

from __future__ import annotations

from pathlib import Path

# Core integrations import StaticPathConfig from this public path, but the
# package re-exports it without listing it in __all__, so pyright flags it.
# The submodule it lives in today did not exist at our 2024.7 floor.
from homeassistant.components.http import (
    StaticPathConfig,  # pyright: ignore[reportPrivateImportUsage]
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry

from .const import (
    CARD_FILENAME,
    CARD_URL,
    CONF_ROOMS,
    CONF_SLUG,
    DATA_CARD_REGISTERED,
    DOMAIN,
    PLATFORMS,
)
from .schedule import HeatingScheduleController

type HeatingScheduleConfigEntry = ConfigEntry[HeatingScheduleController]

CARD_PATH = str(Path(__file__).parent / "www" / CARD_FILENAME)


async def async_setup_entry(
    hass: HomeAssistant, entry: HeatingScheduleConfigEntry
) -> bool:
    """Set up Heating Schedule from a config entry."""
    if not hass.data.get(DATA_CARD_REGISTERED):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, CARD_PATH, cache_headers=False)]
        )
        hass.data[DATA_CARD_REGISTERED] = True

    controller = HeatingScheduleController(hass, entry)
    entry.runtime_data = controller

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # The schedule controller depends on the per-room text/number entities
    # being available, so start it after platforms are forwarded.
    await controller.async_start()

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: HeatingScheduleConfigEntry
) -> bool:
    """Unload a config entry."""
    controller = entry.runtime_data
    await controller.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: HeatingScheduleConfigEntry
) -> None:
    """Reload the entry when the user edits options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: HeatingScheduleConfigEntry,
    device_entry: DeviceEntry,
) -> bool:
    """Handle the 'Delete device' button on the device info page.

    Room devices: drop the room from entry data and clean up the detached
    text entity (HA's device-removal cascade only catches entities attached
    to the device). The update listener then reloads the entry, so the
    schedule controller stops watching the room. Return True so HA proceeds
    to remove the device + its directly-attached entities (number, time).

    Hub device: refuse — there's nothing useful to do per-device on the hub.
    To remove the whole integration the user can delete the config entry
    itself from the integration listing.
    """
    slug = _room_slug_for_device(entry, device_entry)
    if slug is None:
        return False

    rooms = list(entry.data.get(CONF_ROOMS, []))
    remaining = [r for r in rooms if r.get(CONF_SLUG) != slug]
    if len(remaining) == len(rooms):
        # Already gone from entry data (stale device). Let HA clean it up.
        return True

    new_data = dict(entry.data)
    new_data[CONF_ROOMS] = remaining
    hass.config_entries.async_update_entry(entry, data=new_data)

    registry = er.async_get(hass)
    text_eid = registry.async_get_entity_id(
        "text", DOMAIN, f"{entry.entry_id}_{slug}_windows"
    )
    if text_eid:
        registry.async_remove(text_eid)

    return True


def _room_slug_for_device(
    entry: HeatingScheduleConfigEntry, device_entry: DeviceEntry
) -> str | None:
    """Return the room slug for a room device, or None for hub/stranger.

    Room identifiers are (DOMAIN, f"{entry_id}_{slug}"); the hub is
    (DOMAIN, entry_id). Anything else isn't ours.
    """
    prefix = f"{entry.entry_id}_"
    for domain, identifier in device_entry.identifiers:
        if domain != DOMAIN:
            continue
        if identifier == entry.entry_id:
            return None
        if identifier.startswith(prefix):
            return identifier[len(prefix) :]
    return None
