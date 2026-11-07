"""Parser tests. The measurement, test-pattern and blank payloads are real beacons from a
probe; the bytes are the manufacturer-data value after the company ID. The signed, minute
and refusal cases are edits of a real payload.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "iopool_ble"))

import parser as p  # noqa: E402


def test_first_measurement():
    r = p.parse(bytes.fromhex("010101020e02662a4500004f0000"))
    assert r.kind == p.KIND_MEASUREMENT and r.is_measurement
    assert (r.beacon_v, r.mode, r.sequence) == (1, 1, 1)
    assert (r.ph_raw, r.orp_raw, r.temp_ohms, r.cond_raw) == (526, 614, 10821, 0)
    assert (r.activity, r.battery, r.minute) == (1, 30, 0)


def test_second_measurement():
    r = p.parse(bytes.fromhex("010101049c04e329860000aa0000"))
    assert r.is_measurement
    assert (r.ph_raw, r.orp_raw, r.temp_ohms, r.cond_raw) == (1180, 1251, 10630, 0)
    assert (r.activity, r.battery) == (2, 84)


def test_startup_test_pattern_is_not_a_measurement():
    r = p.parse(bytes.fromhex("0101ab01010202030304040a0b0c"))
    assert r.kind == p.KIND_TEST_PATTERN and not r.is_measurement


def test_blank_frame_is_not_a_measurement():
    r = p.parse(bytes.fromhex("0101000000000000000000000000"))
    assert r.kind == p.KIND_BLANK and not r.is_measurement


def test_signed_fields():
    r = p.parse(bytes.fromhex("010102fff6ff9c2a4500004f0000"))
    assert (r.ph_raw, r.orp_raw) == (-10, -100)


def test_minute_is_eleven_bits_across_two_bytes():
    r = p.parse(bytes.fromhex("010101020e02662a4500004fffe0"))
    assert r.minute == 2047


def test_short_and_unknown_layouts_are_refused():
    assert p.parse(bytes.fromhex("010101020e02662a4500004f00")) is None
    assert p.parse(bytes.fromhex("020101020e02662a4500004f0000")) is None
