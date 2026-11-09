"""The connected side: the few things the probe only does when something connects to it.

Readings never need this — they arrive in beacons (coordinator.py). A connection is made
only when a button is pressed, held for one read or write, and dropped. It needs an
adapter or proxy that can connect and that hears the probe; the probe takes one
connection at a time, so it fails while the iopool phone app is connected.

It does two things: read the firmware version, and beep.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

_BASE = "f3a0{:04x}-f0a2-9b06-0c59-1bc4763b5c00"
SERVICE = _BASE.format(0x0001)
CHAR_BEEP = _BASE.format(0x0009)
CHAR_SOFTWARE_VERSION = _BASE.format(0x0011)

BEEP = (200).to_bytes(2, "little")

_lock = asyncio.Lock()


async def _connected[T](
    hass: HomeAssistant,
    address: str,
    uuid: str,
    action: Callable[[BleakClient, BleakGATTCharacteristic], Awaitable[T]],
) -> T:
    """Connect, run one action on one characteristic, disconnect."""
    ble_device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if ble_device is None:
        raise HomeAssistantError(
            f"No Bluetooth adapter or proxy that can connect currently hears {address}"
        )
    async with _lock:
        try:
            client = await establish_connection(
                BleakClientWithServiceCache, ble_device, address, max_attempts=3
            )
        except (BleakError, TimeoutError) as err:
            raise HomeAssistantError(
                f"Could not connect to {address} (is the iopool app connected?): {err}"
            ) from err
        try:
            characteristic = client.services.get_characteristic(uuid)
            if characteristic is None:
                # A stale service cache looks exactly like a missing characteristic: the
                # service is found but none of its characteristics. Discover once afresh
                # before believing it.
                _LOGGER.warning("%s: no %s in the cached services %s; rediscovering",
                                address, uuid, _describe(client))
                await client.clear_cache()
                await client.disconnect()
                client = await establish_connection(
                    BleakClientWithServiceCache, ble_device, address, max_attempts=3,
                    use_services_cache=False,
                )
                characteristic = client.services.get_characteristic(uuid)
            if characteristic is None:
                found = _describe(client)
                _LOGGER.warning("%s has no %s after rediscovery; it offers %s",
                                address, uuid, found)
                raise HomeAssistantError(f"{address} does not offer {uuid}; it offers {found}")
            return await action(client, characteristic)
        except (BleakError, TimeoutError) as err:
            raise HomeAssistantError(f"{address} dropped the request: {err}") from err
        finally:
            await client.disconnect()


def _describe(client: BleakClient) -> dict[str, list[str]]:
    """Every service the probe offers, with its characteristics — for the log."""
    return {s.uuid: sorted(c.uuid for c in s.characteristics) for s in client.services}


async def _write(hass: HomeAssistant, address: str, uuid: str, data: bytes) -> None:
    async def action(client: BleakClient, char: BleakGATTCharacteristic) -> None:
        await client.write_gatt_char(char, data, response="write" in char.properties)

    await _connected(hass, address, uuid, action)


async def read_firmware_version(hass: HomeAssistant, address: str) -> str:
    """Read the probe's firmware version. Changes nothing on the probe."""

    async def action(client: BleakClient, char: BleakGATTCharacteristic) -> str:
        raw = await client.read_gatt_char(char)
        return bytes(raw).split(b"\x00")[0].decode("utf-8", "replace").strip()

    return await _connected(hass, address, CHAR_SOFTWARE_VERSION, action)


async def beep(hass: HomeAssistant, address: str) -> None:
    """Make the probe beep, to find it or to prove the link."""
    await _write(hass, address, CHAR_BEEP, BEEP)
