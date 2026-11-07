"""Buttons for the connected side (active.py). Each press is one short connection."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EcoConfigEntry, active
from .const import DOMAIN
from .coordinator import EcoCoordinator


async def _read_firmware(hass: HomeAssistant, coordinator: EcoCoordinator) -> None:
    coordinator.firmware = await active.read_firmware_version(hass, coordinator.address)
    coordinator.async_update_listeners()


@dataclass(frozen=True, kw_only=True)
class EcoButtonDescription(ButtonEntityDescription):
    press: Callable[[HomeAssistant, EcoCoordinator], Awaitable[None]]


BUTTONS: tuple[EcoButtonDescription, ...] = (
    EcoButtonDescription(
        key="measure_now", translation_key="measure_now",
        press=lambda hass, c: active.measure_now(hass, c.address),
    ),
    EcoButtonDescription(
        key="identify", translation_key="identify",
        entity_category=EntityCategory.DIAGNOSTIC,
        press=lambda hass, c: active.beep(hass, c.address),
    ),
    EcoButtonDescription(
        key="read_firmware", translation_key="read_firmware",
        entity_category=EntityCategory.DIAGNOSTIC, press=_read_firmware,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: EcoConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the buttons for one probe."""
    async_add_entities(EcoButton(entry.runtime_data, d) for d in BUTTONS)


class EcoButton(ButtonEntity):
    """One connected-side action. Always offered: whether the probe can be reached is
    only known by trying, and a failed press raises an error that says why."""

    _attr_has_entity_name = True
    entity_description: EcoButtonDescription

    def __init__(self, coordinator: EcoCoordinator, description: EcoButtonDescription) -> None:
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(dr.CONNECTION_BLUETOOTH, coordinator.address)},
            manufacturer="iopool",
            model="EcO",
            name="iopool EcO",
        )

    async def async_press(self) -> None:
        await self.entity_description.press(self.hass, self.coordinator)
