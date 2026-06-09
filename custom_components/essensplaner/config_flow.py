"""Config flow for Essensplaner."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_HOUSEHOLD_NAME, DOMAIN


class EssensplanerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            household_name = user_input[CONF_HOUSEHOLD_NAME].strip()
            await self.async_set_unique_id(household_name.lower().replace(" ", "_"))
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=household_name,
                data={CONF_HOUSEHOLD_NAME: household_name},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOUSEHOLD_NAME, default="Haushalt"): str,
                }
            ),
            errors=errors,
        )
