"""The iopool EcO beacon decode.

No Home Assistant and no Bluetooth imports, so the tests and any offline tool can load
this file directly.

The input is the manufacturer-data VALUE as Home Assistant hands it over: the bytes that
follow the two-byte company ID (0x074C). Offsets below count from the first value byte.

    0      beacon layout version (only 1 is decoded)
    1      mode (1 = normal)
    2      sequence, increments with each new measurement
    3-4    pH, raw, signed big-endian
    5-6    ORP, raw, signed big-endian
    7-8    thermistor resistance in ohms, big-endian
    9-10   conductivity, raw, big-endian
    11     bits 7-6 activity, bits 5-0 battery / 2
    12-13  minute counter, 11 bits: all of byte 12, then the top 3 bits of byte 13
"""

from __future__ import annotations

from dataclasses import dataclass

COMPANY_ID = 0x074C  # 1868, "iopool s.a."

# Only layout 1 is decoded; any other version is refused rather than guessed.
SUPPORTED_BEACON_V = 1
MIN_LENGTH = 14

KIND_MEASUREMENT = "measurement"
KIND_TEST_PATTERN = "test_pattern"
KIND_BLANK = "blank"

# Sent under the name "EC000000" while the probe starts up: a counting filler, not a
# reading. Decoded naively it gives ph 257, orp 514.
_TEST_PATTERN = bytes.fromhex("ab01010202030304040a0b0c")


@dataclass(frozen=True)
class EcoReading:
    """One decoded beacon. Every measurement field is the raw integer the probe sent."""

    beacon_v: int
    mode: int
    sequence: int
    ph_raw: int
    orp_raw: int
    temp_ohms: int
    cond_raw: int
    activity: int
    battery: int
    minute: int
    kind: str

    @property
    def is_measurement(self) -> bool:
        return self.kind == KIND_MEASUREMENT


def parse(payload: bytes) -> EcoReading | None:
    """Decode one beacon, or None if it is not a layout this file understands."""
    if len(payload) < MIN_LENGTH or payload[0] != SUPPORTED_BEACON_V:
        return None
    body = payload[2:MIN_LENGTH]
    if body == _TEST_PATTERN:
        kind = KIND_TEST_PATTERN
    elif not any(body):
        kind = KIND_BLANK
    else:
        kind = KIND_MEASUREMENT
    return EcoReading(
        beacon_v=payload[0],
        mode=payload[1],
        sequence=payload[2],
        ph_raw=int.from_bytes(payload[3:5], "big", signed=True),
        orp_raw=int.from_bytes(payload[5:7], "big", signed=True),
        temp_ohms=int.from_bytes(payload[7:9], "big"),
        cond_raw=int.from_bytes(payload[9:11], "big"),
        activity=payload[11] >> 6,
        battery=(payload[11] & 0x3F) * 2,
        minute=(payload[12] << 3) | (payload[13] >> 5),
        kind=kind,
    )
