"""Config flow for Reef Factory X3 Dosing Pump."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_EMAIL, CONF_PASSWORD, CONF_SERIAL, DOMAIN
from .coordinator import async_validate_credentials

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_SERIAL): str,
    }
)


class ReefFactoryDoseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Reef Factory X3 Dosing Pump."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            serial = user_input[CONF_SERIAL].strip().upper()
            await self.async_set_unique_id(serial)
            self._abort_if_unique_id_configured()

            try:
                valid = await async_validate_credentials(
                    self.hass,
                    user_input[CONF_EMAIL].strip(),
                    user_input[CONF_PASSWORD],
                )
                if not valid:
                    errors["base"] = "invalid_auth"
                else:
                    return self.async_create_entry(
                        title=f"X3 Dosing Pump {serial}",
                        data={
                            CONF_EMAIL: user_input[CONF_EMAIL].strip(),
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                            CONF_SERIAL: serial,
                        },
                    )
            except HomeAssistantError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
