"""Constants for the Heating Schedule integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "heating_schedule"
PLATFORMS = [Platform.NUMBER, Platform.SWITCH, Platform.TEXT, Platform.TIME]

# Stable entity_id of the integration-owned pause switch, used by the
# schedule controller's _resolve_pause_switch fallback and by the dashboard
# YAML snippet emitted at the end of the config flow.
PAUSE_UNIQUE_SUFFIX = "pause"

# Hard-coded peer for the bidirectional pause mirror. If your install uses
# a different input_boolean to gate pause-related YAML automations, change
# this to its entity_id.
EXTERNAL_PAUSE_BOOLEAN = "input_boolean.heating_paused"

# Config entry keys
CONF_ROOMS = "rooms"
CONF_SETBACK = "setback"

# Per-room keys
CONF_SLUG = "slug"
CONF_NAME = "name"
CONF_CLIMATE_ENTITY = "climate_entity"
CONF_CURRENT_TEMP_ENTITY = "current_temp_entity"
CONF_WINDOW_ENTITY = "window_entity"
CONF_COMFORT_DEFAULT = "comfort_default"
CONF_WINDOWS_DEFAULT = "windows_default"

# Defaults
DEFAULT_SETBACK = 14.0
DEFAULT_COMFORT = 20.0
DEFAULT_COMFORT_MIN = 5.0
DEFAULT_COMFORT_MAX = 30.0
DEFAULT_COMFORT_STEP = 0.5
DEFAULT_WINDOWS_JSON = '[["07:00","22:00"]]'
MAX_WINDOWS = 4
PAUSE_SETTLE_SECONDS = 5

# Card asset
CARD_FILENAME = "heating-window-slider-card.js"
CARD_URL_BASE = f"/{DOMAIN}"
CARD_URL = f"{CARD_URL_BASE}/{CARD_FILENAME}"
