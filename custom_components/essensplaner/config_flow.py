"""Config flow for Essensplaner."""

from __future__ import annotations

from datetime import time
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.helpers import config_validation as cv

from .const import CONF_HOUSEHOLD_NAME, DOMAIN, MEALPLAN_ENTRY_TYPES
from .meal_times import (
    DEFAULT_MEAL_TIMES,
    format_time_value,
    meal_time_option_key,
    parse_time_value,
)


def _meal_times_options_schema(current: dict[str, Any]) -> vol.Schema:
    """Build options schema for meal slot times."""
    fields: dict = {}
    for entry_type in MEALPLAN_ENTRY_TYPES:
        default_start, default_end = DEFAULT_MEAL_TIMES[entry_type]
        start_key = meal_time_option_key(entry_type, "start")
        end_key = meal_time_option_key(entry_type, "end")
        start_default = current.get(start_key, default_start)
        end_default = current.get(end_key, default_end)
        fields[vol.Optional(start_key, default=time(*parse_time_value(start_default)))] = (
            cv.time
        )
        fields[vol.Optional(end_key, default=time(*parse_time_value(end_default)))] = (
            cv.time
        )
    return vol.Schema(fields)


def _normalize_meal_time_options(user_input: dict[str, Any]) -> dict[str, str]:
    """Store meal times as HH:MM strings in config entry options."""
    result: dict[str, str] = {}
    for key, value in user_input.items():
        result[key] = format_time_value(value)
    return result


class EssensplanerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle config flow."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> EssensplanerOptionsFlow:
        """Return options flow."""
        return EssensplanerOptionsFlow(config_entry)

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


class EssensplanerOptionsFlow(OptionsFlow):
    """Handle Essensplaner options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage meal slot times."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data=_normalize_meal_time_options(user_input),
            )

        return self.async_show_form(
            step_id="init",
            data_schema=_meal_times_options_schema(dict(self.config_entry.options)),
        )
