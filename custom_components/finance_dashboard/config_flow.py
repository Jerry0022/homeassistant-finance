"""Config flow for Finance Dashboard integration.

Multi-step flow:
1. user         — Enter Enable Banking API credentials (application_id + private_key_pem)
2. select_bank  — Choose bank from DE institution list
3. authorize    — User redirected to bank for PSD2 authorization
4. accounts     — Assign linked accounts (personal/shared, person)
5. options      — Configure refresh interval, split model, currency
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import DOMAIN, SESSION_MAX_DAYS

_LOGGER = logging.getLogger(__name__)


class FinanceDashboardConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Finance Dashboard."""

    VERSION = 2  # Bumped from 1 (GoCardless) to 2 (Enable Banking)

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._application_id: str = ""
        self._private_key_pem: str = ""
        self._institutions: list[dict[str, Any]] = []
        self._selected_institution: dict[str, Any] = {}
        self._auth_url: str = ""
        self._auth_id: str = ""
        self._session_id: str | None = None
        self._linked_accounts: list[dict[str, Any]] = []
        self._account_details: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Enter Enable Banking API credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._application_id = user_input["application_id"].strip()
            self._private_key_pem = user_input["private_key_pem"].strip()

            if not self._application_id or not self._private_key_pem:
                errors["base"] = "missing_credentials"
            else:
                # Test connection + fetch DE institutions
                try:
                    from .enablebanking_client import EnableBankingClient

                    client = EnableBankingClient(
                        self._application_id, self._private_key_pem
                    )
                    self._institutions = (
                        await client.async_get_institutions("DE")
                    )
                    if self._institutions:
                        # Store credentials securely
                        from .credential_manager import CredentialManager

                        cred_mgr = CredentialManager(self.hass)
                        await cred_mgr.async_initialize()
                        await cred_mgr.async_store_api_credentials(
                            self._application_id, self._private_key_pem
                        )
                        return await self.async_step_select_bank()
                    errors["base"] = "no_institutions"
                except Exception:
                    _LOGGER.exception("Enable Banking connection failed")
                    errors["base"] = "invalid_credentials"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("application_id"): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Required("private_key_pem"): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.TEXT,
                            multiline=True,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "enablebanking_url": "https://enablebanking.com",
                "redirect_url": (
                    f"{self.hass.config.external_url or self.hass.config.internal_url}"
                    f"/api/{DOMAIN}/oauth/callback"
                ),
            },
        )

    async def async_step_select_bank(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: Select a banking institution from the list."""
        errors: dict[str, str] = {}

        if user_input is not None:
            institution_id = user_input.get("institution_id", "")
            # Find selected institution
            for inst in self._institutions:
                if inst["id"] == institution_id:
                    self._selected_institution = inst
                    break

            if self._selected_institution:
                return await self.async_step_authorize()
            errors["base"] = "invalid_institution"

        # Build institution dropdown: {id: "name (BIC)"}
        institution_options = {
            inst["id"]: f"{inst['name']} ({inst.get('bic', '')})"
            for inst in sorted(
                self._institutions, key=lambda x: x["name"]
            )
        }

        return self.async_show_form(
            step_id="select_bank",
            data_schema=vol.Schema(
                {
                    vol.Required("institution_id"): vol.In(
                        institution_options
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "bank_count": str(len(self._institutions)),
            },
        )

    async def async_step_authorize(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: Initiate Enable Banking authorization and redirect user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # User came back from bank — check for auth code
            pending_code = self.hass.data.get(DOMAIN, {}).get(
                "pending_auth_code"
            )

            if pending_code:
                try:
                    from .enablebanking_client import EnableBankingClient

                    client = EnableBankingClient(
                        self._application_id, self._private_key_pem
                    )

                    # Exchange code for session
                    session_data = await client.async_create_session(
                        pending_code
                    )
                    self._session_id = session_data.get("session_id")
                    accounts = session_data.get("accounts", [])

                    # Clear pending code
                    self.hass.data[DOMAIN].pop("pending_auth_code", None)

                    if accounts:
                        self._linked_accounts = accounts
                        # Fetch full account details
                        await self._fetch_account_details(client)
                        return await self.async_step_assign_accounts()
                    errors["base"] = "no_accounts_linked"

                except Exception:
                    _LOGGER.exception(
                        "Failed to create Enable Banking session"
                    )
                    errors["base"] = "connection_failed"
            else:
                errors["base"] = "authorization_pending"
        else:
            # First visit — create auth request
            try:
                from .enablebanking_client import EnableBankingClient

                client = EnableBankingClient(
                    self._application_id, self._private_key_pem
                )

                # Build callback URL
                callback_url = (
                    f"{self.hass.config.external_url or self.hass.config.internal_url}"
                    f"/api/{DOMAIN}/oauth/callback"
                )

                # Calculate session validity
                valid_until = (
                    datetime.now() + timedelta(days=SESSION_MAX_DAYS)
                ).isoformat()

                # Create authorization
                auth_data = await client.async_create_auth(
                    aspsp_name=self._selected_institution["name"],
                    aspsp_country="DE",
                    redirect_url=callback_url,
                    valid_until=valid_until,
                )
                self._auth_url = auth_data.get("url", "")
                self._auth_id = auth_data.get("auth_id", "")

                # Store pending auth for the OAuth callback handler
                self.hass.data.setdefault(DOMAIN, {})
                self.hass.data[DOMAIN]["pending_auth"] = {
                    "auth_id": self._auth_id,
                    "flow_id": self.flow_id,
                }

            except Exception:
                _LOGGER.exception(
                    "Failed to create Enable Banking authorization"
                )
                errors["base"] = "connection_failed"

        bank_name = self._selected_institution.get("name", "your bank")

        return self.async_show_form(
            step_id="authorize",
            data_schema=vol.Schema({}),  # Just a confirm button
            errors=errors,
            description_placeholders={
                "bank_name": bank_name,
                "auth_url": self._auth_url,
            },
        )

    async def async_step_assign_accounts(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4: Assign linked accounts to persons (personal/shared)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Parse account assignments
            account_config = []
            for acc in self._account_details:
                acc_id = acc["id"]
                acc_type = user_input.get(
                    f"type_{acc_id}", "personal"
                )
                acc_person = user_input.get(
                    f"person_{acc_id}", ""
                ).strip()

                account_config.append(
                    {
                        "id": acc_id,
                        "iban": acc.get("iban", ""),
                        "name": acc.get("name", ""),
                        "institution": self._selected_institution.get(
                            "name", ""
                        ),
                        "institution_id": self._selected_institution.get(
                            "id", ""
                        ),
                        "logo": self._selected_institution.get(
                            "logo", ""
                        ),
                        "currency": acc.get("currency", "EUR"),
                        "type": acc_type,
                        "person": acc_person,
                    }
                )

            # Store session in credential manager
            from .credential_manager import CredentialManager

            cred_mgr = CredentialManager(self.hass)
            await cred_mgr.async_initialize()
            valid_until = (
                datetime.now() + timedelta(days=SESSION_MAX_DAYS)
            ).isoformat()
            if self._session_id:
                await cred_mgr.async_store_session(
                    self._session_id, valid_until
                )

            return self.async_create_entry(
                title=f"Finance Dashboard ({self._selected_institution.get('name', '')})",
                data={
                    "configured": True,
                    "institution_id": self._selected_institution.get(
                        "id", ""
                    ),
                    "institution_name": self._selected_institution.get(
                        "name", ""
                    ),
                    "institution_logo": self._selected_institution.get(
                        "logo", ""
                    ),
                    "session_id": self._session_id,
                    "accounts": account_config,
                    # Credentials are NOT stored here — they're in
                    # credential_manager's encrypted .storage/
                },
            )

        # Build form with one type + person field per account
        schema_dict: dict[Any, Any] = {}
        descriptions = []

        for acc in self._account_details:
            acc_id = acc["id"]
            iban_masked = (
                f"****{acc['iban'][-4:]}"
                if len(acc.get("iban", "")) >= 4
                else "****"
            )
            label = f"{acc.get('name', 'Account')} ({iban_masked})"
            descriptions.append(label)

            schema_dict[
                vol.Required(
                    f"type_{acc_id}", default="personal"
                )
            ] = vol.In({"personal": "Personal", "shared": "Shared"})
            schema_dict[
                vol.Optional(f"person_{acc_id}", default="")
            ] = str

        return self.async_show_form(
            step_id="assign_accounts",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "account_count": str(len(self._account_details)),
                "account_list": ", ".join(descriptions),
            },
        )

    async def _fetch_account_details(self, client) -> None:
        """Fetch details for all linked accounts."""
        self._account_details = []
        for account in self._linked_accounts:
            account_id = account.get("id", account) if isinstance(
                account, dict
            ) else account
            try:
                details = await client.async_get_account_details(
                    account_id
                )
                account_data = details.get("account", {})
                account_data["id"] = account_id
                self._account_details.append(account_data)
            except Exception:
                _LOGGER.warning(
                    "Failed to fetch details for account %s",
                    account_id,
                )
                self._account_details.append(
                    {"id": account_id, "name": "Unknown", "iban": ""}
                )

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
                    ): vol.All(
                        vol.Coerce(int), vol.Range(min=15, max=1440)
                    ),
                    vol.Optional(
                        "split_model",
                        default=self.config_entry.options.get(
                            "split_model", "proportional"
                        ),
                    ): vol.In(["proportional", "equal", "custom"]),
                    vol.Optional(
                        "currency",
                        default=self.config_entry.options.get(
                            "currency", "EUR"
                        ),
                    ): str,
                    vol.Optional(
                        "enable_total_balance_sensor",
                        default=self.config_entry.options.get(
                            "enable_total_balance_sensor", False
                        ),
                    ): bool,
                    vol.Optional(
                        "enable_dashboard_panel",
                        default=self.config_entry.options.get(
                            "enable_dashboard_panel", True
                        ),
                    ): bool,
                }
            ),
        )
