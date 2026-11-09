"""Calibration: turn the probe's raw integers into real units from reference readings.

The probe sends raw counts and no scaling, so nothing here ships a constant. A quantity has a value only once enough reference points have been entered for
it; until then it has none, and the entity is unavailable rather than guessed.

No Home Assistant imports, so the tests and any offline tool can load this file directly.

A point is ``{"raw": <probe value>, "ref": <trusted value>}`` (extra keys are kept and
ignored). pH and ORP are a least-squares straight line. Temperature is the thermistor beta
model, ``1/T = a + b*ln(R)`` with T in kelvin, also least squares; references are in °C.
"""

from __future__ import annotations

import math

PH = "ph"
ORP = "orp"
TEMPERATURE = "temperature"
QUANTITIES = (PH, ORP, TEMPERATURE)

MIN_POINTS = 2
_KELVIN = 273.15


def _line(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    """Least-squares (slope, offset), or None when the xs cannot fix a line."""
    n = len(xs)
    if n < MIN_POINTS:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None  # every point at the same raw value
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return slope, my - slope * mx


def fit(quantity: str, points: list[dict]) -> tuple[float, float] | None:
    """The two coefficients for a quantity, or None if its points do not yet fix them."""
    try:
        if quantity == TEMPERATURE:
            usable = [p for p in points if p["raw"] > 0 and p["ref"] > -_KELVIN]
            return _line(
                [math.log(p["raw"]) for p in usable],
                [1.0 / (p["ref"] + _KELVIN) for p in usable],
            )
        return _line([float(p["raw"]) for p in points], [float(p["ref"]) for p in points])
    except (KeyError, TypeError, ValueError):
        return None


def apply(quantity: str, coefficients: tuple[float, float], raw: float) -> float | None:
    """The calibrated value for one raw reading."""
    slope, offset = coefficients
    if quantity != TEMPERATURE:
        return slope * raw + offset
    if raw <= 0:
        return None
    inverse = offset + slope * math.log(raw)
    if inverse <= 0:
        return None
    return 1.0 / inverse - _KELVIN


def convert(quantity: str, points: list[dict], raw: float) -> float | None:
    """Raw to real units in one call; None when uncalibrated."""
    coefficients = fit(quantity, points)
    if coefficients is None:
        return None
    return apply(quantity, coefficients, raw)
