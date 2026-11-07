"""Config flow (find the probe by its manufacturer id) and the calibration options flow.

Calibration lives in the entry's options, per probe: a sealed probe drifts and gets
replaced, so the fit belongs to the device, not to the code. A point pairs the probe's raw
value with a trusted reading taken at the same moment — a buffer solution, an ORP reference
solution, a thermometer.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .calibration import ORP, PH, QUANTITIES, TEMPERATURE, fit
from .const import (
    CONF_CALIBRATION,
    CONF_STALE_AFTER_MINUTES,
    DEFAULT_STALE_AFTER_MINUTES,
    DOMAIN,
)
from .parser import COMPANY_ID, EcoReading

CONF_QUANTITY = "quantity"
CONF_REFERENCE = "reference"
CONF_RAW = "raw"

_RAW_OF = {
    PH: lambda r: r.ph_raw,
    ORP: lambda r: r.orp_raw,
    TEMPERATURE: lambda r: r.temp_ohms,
}


def _title(service_info: BluetoothServiceInfoBleak) -> str:
    return f"iopool EcO ({service_info.address})"


class EcoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle discovery and manual setup."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> EcoOptionsFlow:
        return EcoOptionsFlow()

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """A probe turned up on its own."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if COMPANY_ID not in discovery_info.manufacturer_data:
            return self.async_abort(reason="not_supported")
        self._discovered = discovery_info
        self.context["title_placeholders"] = {"name": _title(discovery_info)}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding a discovered probe."""
        assert self._discovered is not None
        if user_input is not None:
            return self.async_create_entry(
                title=_title(self._discovered),
                data={CONF_ADDRESS: self._discovered.address},
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"name": _title(self._discovered)},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick from the probes Home Assistant can currently hear."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=_title(self._discovered_devices[address]),
                data={CONF_ADDRESS: address},
            )

        current = self._async_current_ids()
        for info in async_discovered_service_info(self.hass, connectable=False):
            if info.address in current or COMPANY_ID not in info.manufacturer_data:
                continue
            self._discovered_devices[info.address] = info
        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {a: _title(i) for a, i in self._discovered_devices.items()}
                    )
                }
            ),
        )


class EcoOptionsFlow(OptionsFlow):
    """Add or clear calibration points, and set the staleness time."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["add_point", "clear_points", "settings"]
        )

    def _reading(self) -> EcoReading | None:
        coordinator = getattr(self.config_entry, "runtime_data", None)
        if coordinator is None or not coordinator.fresh:
            return None
        return coordinator.reading

    def _calibration(self) -> dict[str, list[dict]]:
        stored = self.config_entry.options.get(CONF_CALIBRATION, {})
        return {q: list(stored.get(q, [])) for q in QUANTITIES}

    def _save(self, calibration: dict[str, list[dict]]) -> ConfigFlowResult:
        return self.async_create_entry(
            data={**self.config_entry.options, CONF_CALIBRATION: calibration}
        )

    def _summary(self) -> dict[str, str]:
        """Placeholders: the live raw values and how many points each quantity has."""
        reading, calibration = self._reading(), self._calibration()
        out = {}
        for q in QUANTITIES:
            out[f"{q}_raw"] = "no fresh reading" if reading is None else str(_RAW_OF[q](reading))
            n = len(calibration[q])
            state = "calibrated" if fit(q, calibration[q]) is not None else "not calibrated"
            out[f"{q}_points"] = f"{n} ({state})"
        return out

    async def async_step_add_point(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pair a raw value with a trusted reading. Blank raw = the probe's live value."""
        errors: dict[str, str] = {}
        if user_input is not None:
            quantity = user_input[CONF_QUANTITY]
            raw = user_input.get(CONF_RAW)
            if raw is None:
                reading = self._reading()
                if reading is None:
                    errors["base"] = "no_fresh_reading"
                else:
                    raw = _RAW_OF[quantity](reading)
            if not errors:
                calibration = self._calibration()
                calibration[quantity].append(
                    {
                        "raw": raw,
                        "ref": user_input[CONF_REFERENCE],
                        "at": dt_util.utcnow().isoformat(timespec="seconds"),
                    }
                )
                return self._save(calibration)
        return self.async_show_form(
            step_id="add_point",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_QUANTITY): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(QUANTITIES), translation_key=CONF_QUANTITY
                        )
                    ),
                    vol.Required(CONF_REFERENCE): vol.Coerce(float),
                    vol.Optional(CONF_RAW): vol.Coerce(float),
                }
            ),
            description_placeholders=self._summary(),
            errors=errors,
        )

    async def async_step_clear_points(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Drop every point of the chosen quantities, to start a calibration again."""
        if user_input is not None:
            calibration = self._calibration()
            for quantity in user_input.get(CONF_QUANTITY, []):
                calibration[quantity] = []
            return self._save(calibration)
        return self.async_show_form(
            step_id="clear_points",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_QUANTITY, default=[]): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(QUANTITIES),
                            multiple=True,
                            translation_key=CONF_QUANTITY,
                        )
                    )
                }
            ),
            description_placeholders=self._summary(),
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """How long readings stay available after the last new beacon."""
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, **user_input})
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_STALE_AFTER_MINUTES,
                        default=self.config_entry.options.get(
                            CONF_STALE_AFTER_MINUTES, DEFAULT_STALE_AFTER_MINUTES
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10080))
                }
            ),
        )
