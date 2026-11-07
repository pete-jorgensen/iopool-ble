"""Calibration maths: nothing until two usable points, then least squares."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "iopool_ble"))

import calibration as c  # noqa: E402


def pts(*pairs):
    return [{"raw": raw, "ref": ref} for raw, ref in pairs]


def test_uncalibrated_gives_nothing():
    assert c.convert(c.PH, [], 500) is None
    assert c.convert(c.PH, pts((400, 4.0)), 500) is None


def test_two_points_at_one_raw_value_fix_nothing():
    assert c.fit(c.PH, pts((400, 4.0), (400, 7.0))) is None


def test_two_point_line():
    points = pts((400, 4.0), (700, 7.0))
    assert c.convert(c.PH, points, 400) == pytest.approx(4.0)
    assert c.convert(c.PH, points, 550) == pytest.approx(5.5)


def test_negative_slope_and_negative_raw():
    points = pts((-100, 650.0), (300, 250.0))
    assert c.convert(c.ORP, points, 100) == pytest.approx(450.0)


def test_three_points_are_least_squares():
    slope, offset = c.fit(c.PH, pts((0, 0.0), (1, 1.0), (2, 1.0)))
    assert slope == pytest.approx(0.5) and offset == pytest.approx(1 / 6)


def test_thermistor_beta_model_round_trips():
    # A 10 k / beta 3950 part: R = 10000 * exp(3950 * (1/T - 1/298.15))
    def ohms(celsius):
        return 10000 * math.exp(3950 * (1 / (celsius + 273.15) - 1 / 298.15))

    points = pts((ohms(10), 10.0), (ohms(40), 40.0))
    assert c.convert(c.TEMPERATURE, points, 10000) == pytest.approx(25.0, abs=1e-6)
    assert c.convert(c.TEMPERATURE, points, ohms(37)) == pytest.approx(37.0, abs=1e-6)


def test_thermistor_ignores_impossible_points_and_zero_ohms():
    assert c.fit(c.TEMPERATURE, pts((0, 20.0), (10000, 25.0))) is None
    good = pts((19900, 10.0), (5300, 40.0))
    assert c.convert(c.TEMPERATURE, good, 0) is None


def test_malformed_points_do_not_raise():
    assert c.fit(c.PH, [{"raw": 1}, {"ref": 2}]) is None
