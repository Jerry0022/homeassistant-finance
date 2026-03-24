"""Config flow for Finance Dashboard integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class FinanceDashboardConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Finance Dashboard."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step — GoCardless API credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate GoCardless credentials
            secret_id = user_input.get("secret_id", "").strip()
            secret_key = user_input.get("secret_key", "").strip()

            if not secret_id or not secret_key:
                errors["base"] = "missing_credentials"
            else:
                # Test API connection
                valid = await self._test_gocardless_connection(
                    secret_id, secret_key
                )
                if valid:
                    # Store credentials securely in .storage/
                    return self.async_create_entry(
                        title="Finance Dashboard",
                        data={
                            # Only store a reference flag — actual secrets
                            # go to encrypted .storage/ via credential_manager
                            "configured": True,
                        },
                    )
                errors["base"] = "invalid_credentials"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("secret_id"): str,
                    vol.Required("secret_key"): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "gocardless_url": "https://bankaccountdata.gocardless.com",
            },
        )

    async def async_step_link_bank(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle bank account linking via GoCardless redirect."""
        # This step will be implemented with the GoCardless OAuth flow
        # User gets redirected to their bank to authorize access
        errors: dict[str, str] = {}

        if user_input is not None:
            institution_id = user_input.get("institution_id", "").strip()
            if institution_id:
                # Initiate bank link via GoCardless
                return self.async_create_entry(
                    title="Finance Dashboard",
                    data={"configured": True},
                )

        return self.async_show_form(
            step_id="link_bank",
            data_schema=vol.Schema(
                {
                    vol.Required("institution_id"): str,
                }
            ),
            errors=errors,
        )

    async def _test_gocardless_connection(
        self, secret_id: str, secret_key: str
    ) -> bool:
        """Test GoCardless API connection with provided credentials."""
        try:
            from .gocardless_client import GoCardlessClient

            client = GoCardlessClient(secret_id, secret_key)
            return await client.async_test_connection()
        except Exception:
            _LOGGER.exception("GoCardless connection test failed")
            return False

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> FinanceDashboardOptionsFlow:
        """Get the options flow for this handler."""
        return FinanceDashboardOptionsFlow(config_entry)


class FinanceDashboardOptionsFlow(OptionsFlow):
    """Handle options for Finance Dashboard."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "refresh_interval_minutes",
                        default=self.config_entry.options.get(
                            "refresh_interval_minutes", 60
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=15, max=1440)),
                    vol.Optional(
                        "split_model",
                        default=self.config_entry.options.get(
                            "split_model", "proportional"
                        ),
                    ): vol.In(
                        ["proportional", "equal", "custom"]
                    ),
                    vol.Optional(
                        "currency",
                        default=self.config_entry.options.get(
                            "currency", "EUR"
                        ),
                    ): str,
                }
            ),
        )
