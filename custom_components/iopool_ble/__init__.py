"""iopool EcO pool/spa probe over Bluetooth LE — local, no cloud.

Readings are passive (beacons); the buttons connect briefly (active.py).
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .coordinator import EcoCoordinator

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.SENSOR]

type EcoConfigEntry = ConfigEntry[EcoCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EcoConfigEntry) -> bool:
    """Set up one probe."""
    coordinator = EcoCoordinator(hass, entry, entry.data[CONF_ADDRESS])
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # After the entities exist, so the beacon HA replays on registration reaches them.
    entry.async_on_unload(coordinator.async_start())
    entry.async_on_unload(coordinator.async_start_staleness_tick())
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: EcoConfigEntry) -> None:
    """A calibration point or the staleness setting changed: re-render, no reload needed."""
    entry.runtime_data.async_update_listeners()


async def async_unload_entry(hass: HomeAssistant, entry: EcoConfigEntry) -> bool:
    """Unload one probe."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
