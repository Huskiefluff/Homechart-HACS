"""Config flow for Homechart integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .api import HomechartApi, HomechartApiError, HomechartAuthError
from .const import (
    CONF_API_KEY,
    CONF_URL,
    DEFAULT_NAME,
    DEFAULT_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class HomechartConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Homechart."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api = HomechartApi(
                url=user_input.get(CONF_URL, DEFAULT_URL),
                api_key=user_input[CONF_API_KEY],
            )

            try:
                # Test the connection in executor to avoid blocking
                valid = await self.hass.async_add_executor_job(api.test_connection)

                if valid:
                    # Create unique ID based on API key hash
                    await self.async_set_unique_id(
                        f"homechart_{hash(user_input[CONF_API_KEY])}"
                    )
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=user_input.get(CONF_NAME, DEFAULT_NAME),
                        data=user_input,
                    )
                else:
                    errors["base"] = "invalid_auth"

            except HomechartAuthError:
                errors["base"] = "invalid_auth"
            except HomechartApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Optional(CONF_URL, default=DEFAULT_URL): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
                    ),
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): selector.TextSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is not None:
            api = HomechartApi(
                url=user_input.get(CONF_URL, DEFAULT_URL),
                api_key=user_input[CONF_API_KEY],
            )

            try:
                valid = await self.hass.async_add_executor_job(api.test_connection)

                if valid:
                    return self.async_update_reload_and_abort(
                        entry,
                        data={**entry.data, **user_input},
                    )
                else:
                    errors["base"] = "invalid_auth"

            except HomechartAuthError:
                errors["base"] = "invalid_auth"
            except HomechartApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_API_KEY, 
                        default=entry.data.get(CONF_API_KEY, "")
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Optional(
                        CONF_URL, 
                        default=entry.data.get(CONF_URL, DEFAULT_URL)
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> HomechartOptionsFlow:
        """Get the options flow for this handler."""
        return HomechartOptionsFlow(config_entry)


class HomechartOptionsFlow(config_entries.OptionsFlow):
    """Handle Homechart options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "show_completed_tasks",
                        default=self.config_entry.options.get(
                            "show_completed_tasks", False
                        ),
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        "upcoming_days",
                        default=self.config_entry.options.get("upcoming_days", 7),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=30,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )
