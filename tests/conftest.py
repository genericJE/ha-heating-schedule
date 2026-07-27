"""Shared fixtures for Heating Schedule tests."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from pytest_homeassistant_custom_component.common import async_mock_service


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading of the custom integration in every test."""


@pytest.fixture(autouse=True)
def climate_calls(hass: HomeAssistant) -> list[ServiceCall]:
    """Register climate.set_temperature and capture the writes.

    No real climate platform is loaded in tests, so without this the
    controller's write path raises ServiceNotFound. That only happens when
    it actually decides to write, which depends on the wall clock — a run
    inside the schedule window is quiet, one outside it pushes setback — so
    the failure looked intermittent. Autouse keeps every test time-agnostic.
    """
    return async_mock_service(hass, "climate", "set_temperature")
