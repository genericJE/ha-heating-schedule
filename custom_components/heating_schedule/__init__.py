"""Heating Schedule integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CARD_FILENAME, CARD_URL, DOMAIN, PLATFORMS
from .schedule import HeatingScheduleController

_LOGGER = logging.getLogger(__name__)

type HeatingScheduleConfigEntry = ConfigEntry[HeatingScheduleController]

CARD_PATH = str(Path(__file__).parent / "www" / CARD_FILENAME)


async def async_setup_entry(
    hass: HomeAssistant, entry: HeatingScheduleConfigEntry
) -> bool:
    """Set up Heating Schedule from a config entry."""
    if not hass.data.get(f"{DOMAIN}_card_registered"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, CARD_PATH, cache_headers=False)]
        )
        hass.data[f"{DOMAIN}_card_registered"] = True

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
