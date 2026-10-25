"""Setup-wizard HTTP endpoints for Finance (read-side only).

Bank linking (authorize, OAuth callback, completion) now lives in the config
subentry flow (``config_flow.BankSubentryFlow``).  What remains serves the
legacy panel wizard: status, HA users, institution catalog, account settings.
"""

from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from ..const import DOMAIN
from ._helpers import (
    _cache_is_fresh,
    _get_manager,
    _get_setup_client,
    async_load_cached_institutions,
    async_save_cached_institutions,
)

_LOGGER = logging.getLogger(__name__)


class FinanceDashboardSetupStatusView(HomeAssistantView):
    """Check setup status — is a bank connected?"""

    url = f"/api/{DOMAIN}/setup/status"
    name = f"api:{DOMAIN}:setup_status"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Return current setup status."""
        hass = request.app["hass"]
        entry = hass.data.get(DOMAIN, {}).get("entry")

        if not entry:
            return self.json({"configured": False, "has_entry": False})

        configured = entry.data.get("configured", False)
        has_pending_code = bool(hass.data.get(DOMAIN, {}).get("pending_auth_code"))
        # Include pending session accounts for step 3 of wizard
        pending_accounts = hass.data.get(DOMAIN, {}).get("pending_accounts", [])

        # Sanitize account details for frontend (no raw IBANs)
        raw_accounts = entry.data.get("accounts", [])
        safe_accounts = []
        for acc in raw_accounts:
            iban = acc.get("iban", "")
            safe_accounts.append(
                {
                    "id": acc.get("id", ""),
                    "name": acc.get("name", ""),
                    "custom_name": acc.get("custom_name", ""),
                    "iban_masked": (f"****{iban[-4:]}" if len(iban) >= 4 else "****"),
                    "institution": acc.get("institution", ""),
                    "institution_id": acc.get("institution_id", ""),
                    "logo": acc.get("logo", ""),
                    "type": acc.get("type", "personal"),
                    "ha_users": acc.get("ha_users", []),
                    "person": acc.get("person", ""),
                }
            )

        # Surface any error from the OAuth callback so the wizard can
        # stop polling and display a meaningful message instead of timing
        # out after 5 minutes.
        setup_error = hass.data.get(DOMAIN, {}).get("pending_setup_error")

        result = {
            "configured": configured,
            "has_entry": True,
            "institution_name": entry.data.get("institution_name", ""),
            "account_count": len(raw_accounts),
            "accounts": safe_accounts,
            "pending_auth_code": has_pending_code,
            "pending_accounts": pending_accounts,
            "setup_error": setup_error,
        }
        return self.json(result)


class FinanceDashboardSetupUsersView(HomeAssistantView):
    """Return HA users for account assignment in setup wizard."""

    url = f"/api/{DOMAIN}/setup/users"
    name = f"api:{DOMAIN}:setup_users"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Return list of HA users (id + name)."""
        hass = request.app["hass"]

        users = await hass.auth.async_get_users()
        user_list = [
            {"id": user.id, "name": user.name or user.id}
            for user in users
            if user.is_active and not user.system_generated
        ]
        return self.json({"users": user_list})


class FinanceDashboardSetupInstitutionsView(HomeAssistantView):
    """List available banking institutions for DE."""

    url = f"/api/{DOMAIN}/setup/institutions"
    name = f"api:{DOMAIN}:setup_institutions"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Fetch the DE bank list.

        The ``/aspsps`` catalog is served by Enable Banking itself, not by a
        bank, so it neither spends nor is bound by the 4/day per-ASPSP quota.
        Gating it would lock a rate-limited user out of connecting any new
        bank — hence ``enforce_rate_limit=False``.

        A fresh cache short-circuits the API entirely; a stale cache is used
        as a fallback when the API fails, so an outage degrades the wizard to
        an older list instead of an empty one.

        Always returns HTTP 200 with error details in the body so the
        frontend can inspect error_type reliably.  HA's callApi() throws
        on non-200 responses, swallowing the JSON body.
        """
        hass = request.app["hass"]

        cached, cached_at = await async_load_cached_institutions(hass)
        if cached and _cache_is_fresh(cached_at):
            _LOGGER.debug("Serving %d institutions from fresh cache", len(cached))
            return self.json({"institutions": cached})

        def _fallback(error_msg: str, error_type: str) -> web.Response:
            """Prefer a stale catalog over an error the user cannot act on."""
            if cached:
                _LOGGER.warning(
                    "Institution fetch failed (%s) — serving %d cached entries",
                    error_type,
                    len(cached),
                )
                return self.json({"institutions": cached, "cached_at": cached_at})
            return self.json({"error": error_msg, "error_type": error_type})

        try:
            from ..enablebanking_client import RateLimitExceeded

            client = await _get_setup_client(hass, enforce_rate_limit=False)
            institutions = await client.async_get_institutions("DE")
            _LOGGER.debug(
                "Fetched %d institutions from Enable Banking",
                len(institutions),
            )
            if not institutions:
                return _fallback("Enable Banking returned an empty bank list", "api_error")
            await async_save_cached_institutions(hass, institutions)
            return self.json({"institutions": institutions})

        except RateLimitExceeded as exc:
            return _fallback(str(exc), "rate_limited")
        except RuntimeError as exc:
            error_msg = str(exc)
            _LOGGER.warning("Setup client error: %s", error_msg)
            return _fallback(error_msg, "no_credentials")
        except TimeoutError:
            _LOGGER.error("Timeout fetching institutions from Enable Banking API")
            return _fallback("Enable Banking API timeout — please try again", "timeout")
        except Exception as exc:
            _LOGGER.exception("Failed to fetch institutions")
            error_type = "api_error"
            error_msg = f"Failed to fetch institutions: {str(exc)[:200]}"
            exc_msg = str(exc).lower()
            if "401" in exc_msg or "403" in exc_msg or "unauthorized" in exc_msg:
                error_type = "invalid_credentials"
                error_msg = "API credentials rejected by Enable Banking"
            return _fallback(error_msg, error_type)


class FinanceDashboardSetupUpdateAccountsView(HomeAssistantView):
    """Update account settings (name, type, person assignment)."""

    url = f"/api/{DOMAIN}/setup/update_accounts"
    name = f"api:{DOMAIN}:setup_update_accounts"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Update account metadata in config entry."""
        hass = request.app["hass"]
        entry = hass.data.get(DOMAIN, {}).get("entry")

        if not entry:
            return self.json({"error": "Not configured"}, status_code=404)

        try:
            body = await request.json()
        except Exception:
            return self.json({"error": "Invalid JSON body"}, status_code=400)

        updates = body.get("accounts", [])
        if not updates:
            return self.json(
                {"error": "No account data provided"},
                status_code=400,
            )

        # Merge updates into existing account config
        existing = list(entry.data.get("accounts", []))
        for update in updates:
            acc_id = update.get("id")
            if not acc_id:
                continue
            for acc in existing:
                if acc.get("id") == acc_id:
                    if "custom_name" in update:
                        acc["custom_name"] = update["custom_name"]
                    if "type" in update:
                        acc["type"] = update["type"]
                    if "ha_users" in update:
                        acc["ha_users"] = update["ha_users"]
                    if "person" in update:
                        acc["person"] = update["person"]
                    break

        # Update config entry
        new_data = {**entry.data, "accounts": existing}
        hass.config_entries.async_update_entry(entry, data=new_data)

        # Update manager if running
        manager = _get_manager(hass)
        if manager:
            manager.async_set_accounts(existing)

        _LOGGER.info(
            "Updated account settings for %d accounts",
            len(updates),
        )
        return self.json({"success": True})
