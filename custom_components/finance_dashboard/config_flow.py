"""Config flow for Finance Dashboard integration.

Multi-step flow:
1. user         — Enter GoCardless API credentials (secret_id + secret_key)
2. select_bank  — Choose bank from DE institution list
3. authorize    — User redirected to bank for PSD2 authorization
4. accounts     — Assign linked accounts (personal/shared, person)
5. options      — Configure refresh interval, split model, currency
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_entry_flow

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Requisition status constants
STATUS_LINKED = "LN"
STATUS_REJECTED = "RJ"
STATUS_EXPIRED = "EX"


class FinanceDashboardConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Finance Dashboard."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._secret_id: str = ""
        self._secret_key: str = ""
        self._institutions: list[dict[str, Any]] = []
        self._selected_institution: dict[str, Any] = {}
        self._agreement_id: str | None = None
        self._requisition_id: str | None = None
        self._requisition_link: str = ""
        self._linked_accounts: list[str] = []
        self._account_details: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Enter GoCardless API credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._secret_id = user_input["secret_id"].strip()
            self._secret_key = user_input["secret_key"].strip()

            if not self._secret_id or not self._secret_key:
                errors["base"] = "missing_credentials"
            else:
                # Test connection + fetch DE institutions in one go
                try:
                    from .gocardless_client import GoCardlessClient

                    client = GoCardlessClient(
                        self._secret_id, self._secret_key
                    )
                    # This also validates credentials (gets token first)
                    self._institutions = (
                        await client.async_get_institutions("DE")
                    )
                    if self._institutions:
                        # Store credentials securely
                        from .credential_manager import CredentialManager

                        cred_mgr = CredentialManager(self.hass)
                        await cred_mgr.async_initialize()
                        await cred_mgr.async_store_api_credentials(
                            self._secret_id, self._secret_key
                        )
                        return await self.async_step_select_bank()
                    errors["base"] = "no_institutions"
                except Exception:
                    _LOGGER.exception("GoCardless connection failed")
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
                "gocardless_url": (
                    "https://bankaccountdata.gocardless.com"
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
        """Step 3: Create requisition and redirect user to bank."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # User came back from bank — check requisition status
            if self._requisition_id:
                try:
                    from .gocardless_client import GoCardlessClient

                    client = GoCardlessClient(
                        self._secret_id, self._secret_key
                    )
                    requisition = await client.async_get_requisition(
                        self._requisition_id
                    )
                    status = requisition.get("status", "")

                    if status == STATUS_LINKED:
                        self._linked_accounts = requisition.get(
                            "accounts", []
                        )
                        if self._linked_accounts:
                            # Fetch account details for assignment step
                            await self._fetch_account_details(client)
                            return await self.async_step_assign_accounts()
                        errors["base"] = "no_accounts_linked"
                    elif status == STATUS_REJECTED:
                        errors["base"] = "bank_rejected"
                    elif status == STATUS_EXPIRED:
                        errors["base"] = "authorization_expired"
                    else:
                        errors["base"] = "authorization_pending"
                except Exception:
                    _LOGGER.exception("Failed to check requisition")
                    errors["base"] = "connection_failed"
        else:
            # First visit — create requisition
            try:
                from .gocardless_client import GoCardlessClient

                client = GoCardlessClient(
                    self._secret_id, self._secret_key
                )

                # Create end-user agreement
                agreement = await client.async_create_agreement(
                    institution_id=self._selected_institution["id"],
                    max_historical_days=90,
                    access_valid_for_days=90,
                )
                self._agreement_id = agreement["id"]

                # Build callback URL
                callback_url = (
                    f"{self.hass.config.external_url or self.hass.config.internal_url}"
                    f"/api/{DOMAIN}/oauth/callback"
                )

                # Create requisition
                requisition = await client.async_create_requisition(
                    institution_id=self._selected_institution["id"],
                    redirect_url=callback_url,
                    agreement_id=self._agreement_id,
                    reference=str(uuid.uuid4()),
                )
                self._requisition_id = requisition["id"]
                self._requisition_link = requisition.get("link", "")

                # Store requisition ID for the OAuth callback handler
                self.hass.data.setdefault(DOMAIN, {})
                self.hass.data[DOMAIN]["pending_requisition"] = {
                    "id": self._requisition_id,
                    "flow_id": self.flow_id,
                }

            except Exception:
                _LOGGER.exception("Failed to create requisition")
                errors["base"] = "connection_failed"

        bank_name = self._selected_institution.get("name", "your bank")

        return self.async_show_form(
            step_id="authorize",
            data_schema=vol.Schema({}),  # Just a confirm button
            errors=errors,
            description_placeholders={
                "bank_name": bank_name,
                "auth_url": self._requisition_link,
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
                    "requisition_id": self._requisition_id,
                    "agreement_id": self._agreement_id,
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
        for account_id in self._linked_accounts:
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
