"""Sensors for one probe: the raw integers it sends, and the calibrated values.

The raw sensors need no calibration and are always present. A calibrated sensor is
unavailable until its quantity has enough reference points (calibration.py) — it never shows
a guess. Everything goes unavailable when the probe stops sending new beacons.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.bluetooth.passive_update_coordinator import (
    PassiveBluetoothCoordinatorEntity,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EcoConfigEntry
from .calibration import ORP, PH, TEMPERATURE, apply, fit
from .const import DOMAIN
from .coordinator import EcoCoordinator
from .parser import EcoReading

OHM = "Ω"


@dataclass(frozen=True, kw_only=True)
class EcoRawDescription(SensorEntityDescription):
    """A field taken straight from the beacon."""

    value: Callable[[EcoReading], int]


@dataclass(frozen=True, kw_only=True)
class EcoCalibratedDescription(SensorEntityDescription):
    """A quantity converted through the user's calibration."""

    quantity: str
    raw: Callable[[EcoReading], int]


_DIAG = EntityCategory.DIAGNOSTIC
_MEAS = SensorStateClass.MEASUREMENT

RAW: tuple[EcoRawDescription, ...] = (
    EcoRawDescription(key="ph_raw", translation_key="ph_raw", state_class=_MEAS,
                      entity_category=_DIAG, value=lambda r: r.ph_raw),
    EcoRawDescription(key="orp_raw", translation_key="orp_raw", state_class=_MEAS,
                      entity_category=_DIAG, value=lambda r: r.orp_raw),
    EcoRawDescription(key="temp_ohms", translation_key="temp_ohms", state_class=_MEAS,
                      native_unit_of_measurement=OHM, entity_category=_DIAG,
                      value=lambda r: r.temp_ohms),
    EcoRawDescription(key="cond_raw", translation_key="cond_raw", state_class=_MEAS,
                      entity_category=_DIAG, value=lambda r: r.cond_raw),
    EcoRawDescription(key="battery", device_class=SensorDeviceClass.BATTERY,
                      native_unit_of_measurement=PERCENTAGE, state_class=_MEAS,
                      entity_category=_DIAG, value=lambda r: r.battery),
    EcoRawDescription(key="sequence", translation_key="sequence", entity_category=_DIAG,
                      value=lambda r: r.sequence),
    EcoRawDescription(key="mode", translation_key="mode", entity_category=_DIAG,
                      entity_registry_enabled_default=False, value=lambda r: r.mode),
    EcoRawDescription(key="activity", translation_key="activity", entity_category=_DIAG,
                      entity_registry_enabled_default=False, value=lambda r: r.activity),
    EcoRawDescription(key="minute", translation_key="minute", entity_category=_DIAG,
                      entity_registry_enabled_default=False, value=lambda r: r.minute),
)

CALIBRATED: tuple[EcoCalibratedDescription, ...] = (
    EcoCalibratedDescription(key="ph", device_class=SensorDeviceClass.PH, state_class=_MEAS,
                             suggested_display_precision=2, quantity=PH,
                             raw=lambda r: r.ph_raw),
    EcoCalibratedDescription(key="orp", translation_key="orp", state_class=_MEAS,
                             device_class=SensorDeviceClass.VOLTAGE,
                             native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
                             suggested_display_precision=0, quantity=ORP,
                             raw=lambda r: r.orp_raw),
    EcoCalibratedDescription(key="temperature", device_class=SensorDeviceClass.TEMPERATURE,
                             native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                             state_class=_MEAS, suggested_display_precision=1,
                             quantity=TEMPERATURE, raw=lambda r: r.temp_ohms),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: EcoConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the sensors for one probe."""
    coordinator = entry.runtime_data
    async_add_entities(
        [EcoRawSensor(coordinator, d) for d in RAW]
        + [EcoCalibratedSensor(coordinator, d) for d in CALIBRATED]
        + [EcoLastReadingSensor(coordinator), EcoFrameKindSensor(coordinator),
           EcoRssiSensor(coordinator), EcoFirmwareSensor(coordinator)]
    )


class EcoEntity(PassiveBluetoothCoordinatorEntity[EcoCoordinator], SensorEntity):
    """Common identity; available only while the latest measurement is fresh."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EcoCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(dr.CONNECTION_BLUETOOTH, coordinator.address)},
            manufacturer="iopool",
            model="EcO",
            name="iopool EcO",
        )

    @property
    def available(self) -> bool:
        return self.coordinator.fresh


class EcoRawSensor(EcoEntity):
    """One beacon field, unscaled."""

    entity_description: EcoRawDescription

    def __init__(self, coordinator: EcoCoordinator, description: EcoRawDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | None:
        reading = self.coordinator.reading
        return None if reading is None else self.entity_description.value(reading)


class EcoCalibratedSensor(EcoEntity):
    """A real-unit value; unavailable until its quantity is calibrated."""

    entity_description: EcoCalibratedDescription

    def __init__(
        self, coordinator: EcoCoordinator, description: EcoCalibratedDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    def _coefficients(self) -> tuple[float, float] | None:
        quantity = self.entity_description.quantity
        return fit(quantity, self.coordinator.points(quantity))

    @property
    def available(self) -> bool:
        return self.coordinator.fresh and self._coefficients() is not None

    @property
    def native_value(self) -> float | None:
        reading, coefficients = self.coordinator.reading, self._coefficients()
        if reading is None or coefficients is None:
            return None
        return apply(
            self.entity_description.quantity,
            coefficients,
            self.entity_description.raw(reading),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        coefficients = self._coefficients()
        return {
            "calibration_points": len(
                self.coordinator.points(self.entity_description.quantity)
            ),
            "calibration_slope": None if coefficients is None else coefficients[0],
            "calibration_offset": None if coefficients is None else coefficients[1],
        }


class EcoLastReadingSensor(EcoEntity):
    """When the latest NEW measurement arrived. Stays available so staleness is visible."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = _DIAG
    _attr_translation_key = "last_reading"

    def __init__(self, coordinator: EcoCoordinator) -> None:
        super().__init__(coordinator, "last_reading")

    @property
    def available(self) -> bool:
        return self.coordinator.reading_at is not None

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.reading_at


class EcoFrameKindSensor(EcoEntity):
    """What the latest beacon was: a measurement, or one of the start-up fillers."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["measurement", "test_pattern", "blank"]
    _attr_entity_category = _DIAG
    _attr_translation_key = "last_frame"

    def __init__(self, coordinator: EcoCoordinator) -> None:
        super().__init__(coordinator, "last_frame")

    @property
    def available(self) -> bool:
        return self.coordinator.last_frame_kind is not None

    @property
    def native_value(self) -> str | None:
        return self.coordinator.last_frame_kind


class EcoRssiSensor(EcoEntity):
    """Signal strength of the latest beacon."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = _MEAS
    _attr_entity_category = _DIAG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: EcoCoordinator) -> None:
        super().__init__(coordinator, "rssi")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.rssi


class EcoFirmwareSensor(EcoEntity):
    """The probe's firmware version, once the Read firmware version button has fetched it."""

    _attr_entity_category = _DIAG
    _attr_translation_key = "firmware"

    def __init__(self, coordinator: EcoCoordinator) -> None:
        super().__init__(coordinator, "firmware")

    @property
    def available(self) -> bool:
        return self.coordinator.firmware is not None

    @property
    def native_value(self) -> str | None:
        return self.coordinator.firmware
