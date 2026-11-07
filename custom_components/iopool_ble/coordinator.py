"""Holds the latest beacon from one probe and decides whether it is still fresh.

Passive: every reading arrives in an advertisement, through
whichever adapter or proxy Home Assistant hears it on.

Freshness is this integration's own, not Home Assistant's "device is in range". A probe
that has stopped measuring must not look alive, so readings go
unavailable when no NEW beacon has arrived within the configured time — a probe that keeps
repeating one old beacon is stale, however recently it was heard.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from homeassistant.components.bluetooth import (
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.components.bluetooth.passive_update_coordinator import (
    PassiveBluetoothDataUpdateCoordinator,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CALIBRATION,
    CONF_STALE_AFTER_MINUTES,
    DEFAULT_STALE_AFTER_MINUTES,
)
from .parser import COMPANY_ID, EcoReading, parse

_LOGGER = logging.getLogger(__name__)


class EcoCoordinator(PassiveBluetoothDataUpdateCoordinator):
    """The latest measurement from one EcO."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, address: str) -> None:
        super().__init__(
            hass, _LOGGER, address, BluetoothScanningMode.PASSIVE, connectable=False
        )
        self.entry = entry
        self.reading: EcoReading | None = None  # the latest MEASUREMENT beacon
        self.reading_at: datetime | None = None
        self.last_frame_kind: str | None = None  # the latest beacon of any kind
        self.rssi: int | None = None
        self.firmware: str | None = None  # known only after the button reads it
        self._last_payload: bytes | None = None

    @property
    def stale_after(self) -> timedelta:
        return timedelta(
            minutes=self.entry.options.get(
                CONF_STALE_AFTER_MINUTES, DEFAULT_STALE_AFTER_MINUTES
            )
        )

    @property
    def fresh(self) -> bool:
        """True while the latest measurement is recent enough to show."""
        return (
            self.reading_at is not None
            and dt_util.utcnow() - self.reading_at <= self.stale_after
        )

    def points(self, quantity: str) -> list[dict]:
        """The calibration points entered for a quantity."""
        return list(self.entry.options.get(CONF_CALIBRATION, {}).get(quantity, []))

    @callback
    def async_start_staleness_tick(self) -> CALLBACK_TYPE:
        """Re-render once a minute so a reading turns unavailable when it ages out."""

        @callback
        def _tick(_now: datetime) -> None:
            self.async_update_listeners()

        return async_track_time_interval(self.hass, _tick, timedelta(minutes=1))

    @callback
    def _async_handle_bluetooth_event(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        payload = service_info.manufacturer_data.get(COMPANY_ID)
        reading = parse(payload) if payload is not None else None
        if reading is None:
            if payload is not None:
                _LOGGER.debug("Unrecognised beacon from %s: %s", self.address, payload.hex())
        else:
            self.rssi = service_info.rssi
            self.last_frame_kind = reading.kind
            if reading.is_measurement and payload != self._last_payload:
                self._last_payload = payload
                self.reading = reading
                # service_info.time is monotonic; on start-up HA replays a beacon it heard
                # earlier, and that one must not be stamped "now".
                age = max(0.0, time.monotonic() - service_info.time)
                self.reading_at = dt_util.utcnow() - timedelta(seconds=age)
        super()._async_handle_bluetooth_event(service_info, change)
