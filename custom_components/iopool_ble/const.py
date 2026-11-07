"""Constants for the iopool EcO integration."""

from __future__ import annotations

DOMAIN = "iopool_ble"

# entry.options
CONF_CALIBRATION = "calibration"  # {quantity: [{"raw": .., "ref": .., "at": iso}, ...]}
CONF_STALE_AFTER_MINUTES = "stale_after_minutes"

# How long after the last NEW beacon the readings stay available. The probe measures
# every 15 minutes in its normal mode, so the default tolerates three missed beacons.
DEFAULT_STALE_AFTER_MINUTES = 60
