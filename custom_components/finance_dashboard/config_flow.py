"""Config flow for Finance integration.

Minimal flow: only collects Enable Banking API credentials.
Bank selection, authorization, and account assignment happen
in the Finance panel (setup wizard overlay).
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
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

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _normalize_pem(raw: str) -> str:
    """Normalize a PEM private key that may have lost newlines.

    Handles:
    - Correct PEM (returned as-is)
    - PEM with all newlines stripped (re-wrapped at 64 chars)
    - PEM with \\n literal strings instead of real newlines
    - Extra whitespace between lines
    """
    if not raw:
        return raw

    # Replace literal \n sequences with real newlines
    normalized = raw.replace("\\n", "\n")

    # If it already has proper PEM structure, return as-is
    if "-----BEGIN" in normalized and "\n" in normalized.split("-----")[2]:
        return normalized.strip()

    # Strip headers/footers and all whitespace to get raw base64
    body = normalized
    for marker in (
        "-----BEGIN PRIVATE KEY-----",
        "-----END PRIVATE KEY-----",
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----END RSA PRIVATE KEY-----",
    ):
        body = body.replace(marker, "")
    body = body.replace("\n", "").replace("\r", "").replace(" ", "")

    if not body:
        return raw

    # Detect header type
    if "RSA PRIVATE KEY" in normalized:
        header = "-----BEGIN RSA PRIVATE KEY-----"
        footer = "-----END RSA PRIVATE KEY-----"
    else:
        header = "-----BEGIN PRIVATE KEY-----"
        footer = "-----END PRIVATE KEY-----"

    # Re-wrap at 64 characters per line (PEM standard)
    lines = [body[i : i + 64] for i in range(0, len(body), 64)]
    return f"{header}\n" + "\n".join(lines) + f"\n{footer}"


class FinanceDashboardConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Finance.

    Single step: validate Enable Banking API credentials, then create
    the config entry immediately. Bank setup continues in the panel.
    """

    VERSION = 3  # v1=GoCardless, v2=Enable Banking full flow, v3=credentials-only

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect Enable Banking API credentials and create entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            application_id = user_input["application_id"].strip()
            private_key_pem = _normalize_pem(user_input["private_key_pem"].strip())

            if not application_id or not private_key_pem:
                errors["base"] = "missing_credentials"
            else:
                # Validate credentials by constructing client + fetching institutions
                try:
                    from .enablebanking_client import EnableBankingClient

                    client = EnableBankingClient(application_id, private_key_pem)
                except (ValueError, TypeError) as exc:
                    _LOGGER.error("Failed to load PEM private key: %s", exc)
                    errors["base"] = "invalid_key_format"
                except Exception:
                    _LOGGER.exception("Unexpected error loading credentials")
                    errors["base"] = "invalid_key_format"
                else:
                    try:
                        institutions = await client.async_get_institutions("DE")
                    except aiohttp.ClientResponseError as exc:
                        _LOGGER.error(
                            "Enable Banking API rejected request: HTTP %s — %s",
                            exc.status,
                            exc.message,
                        )
                        if exc.status in (401, 403):
                            errors["base"] = "invalid_credentials"
                        else:
                            errors["base"] = "connection_failed"
                    except aiohttp.ClientError as exc:
                        _LOGGER.error(
                            "Network error contacting Enable Banking: %s",
                            exc,
                        )
                        errors["base"] = "connection_failed"
                    except Exception:
                        _LOGGER.exception("Enable Banking connection failed")
                        errors["base"] = "invalid_credentials"
                    else:
                        if not institutions:
                            errors["base"] = "no_institutions"
                        else:
                            # Credentials valid — store encrypted and create entry
                            from .credential_manager import (
                                CredentialManager,
                            )

                            cred_mgr = CredentialManager(self.hass)
                            await cred_mgr.async_initialize()
                            await cred_mgr.async_store_api_credentials(
                                application_id,
                                private_key_pem,
                            )

                            from homeassistant.components.persistent_notification import (
                                async_create as pn_async_create,
                            )

                            pn_async_create(
                                self.hass,
                                message=(
                                    "Öffne das Finance-Panel in der Sidebar, "
                                    "um deine erste Bank zu verbinden."
                                ),
                                title="Finance Dashboard eingerichtet",
                                notification_id="fd_setup_complete",
                            )
                            return self.async_create_entry(
                                title="Finance",
                                data={"configured": False},
                            )

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

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> FinanceDashboardOptionsFlow:
        """Get the options flow for this handler."""
        return FinanceDashboardOptionsFlow(config_entry)


class FinanceDashboardOptionsFlow(OptionsFlow):
    """Handle options for Finance."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "refresh_interval_minutes",
                        default=self.config_entry.options.get("refresh_interval_minutes", 60),
                    ): vol.All(vol.Coerce(int), vol.Range(min=15, max=1440)),
                    vol.Optional(
                        "split_model",
                        default=self.config_entry.options.get("split_model", "proportional"),
                    ): vol.In(["proportional", "equal", "custom"]),
                    vol.Optional(
                        "currency",
                        default=self.config_entry.options.get("currency", "EUR"),
                    ): str,
                    vol.Optional(
                        "enable_total_balance_sensor",
                        default=self.config_entry.options.get("enable_total_balance_sensor", False),
                    ): bool,
                    vol.Optional(
                        "enable_dashboard_panel",
                        default=self.config_entry.options.get("enable_dashboard_panel", True),
                    ): bool,
                    vol.Optional(
                        "demo_mode",
                        default=self.config_entry.options.get("demo_mode", False),
                    ): bool,
                }
            ),
        )
