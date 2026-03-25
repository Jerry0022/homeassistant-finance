"""HTTP API endpoints for Finance.

Provides REST endpoints for the frontend panel and Lovelace cards
to interact with the integration.

SECURITY:
- All endpoints require HA authentication (Bearer token) except OAuth callback
- No financial data in URL parameters
- Responses stripped of sensitive fields (tokens, IBANs truncated)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN, SESSION_MAX_DAYS

_LOGGER = logging.getLogger(__name__)


async def async_register_api(hass: HomeAssistant) -> None:
    """Register HTTP API endpoints."""
    hass.http.register_view(FinanceDashboardOAuthCallbackView())
    hass.http.register_view(FinanceDashboardStaticView())
    hass.http.register_view(FinanceDashboardBalanceView())
    hass.http.register_view(FinanceDashboardTransactionsView())
    hass.http.register_view(FinanceDashboardSummaryView())
    # Setup wizard endpoints
    hass.http.register_view(FinanceDashboardSetupStatusView())
    hass.http.register_view(FinanceDashboardSetupInstitutionsView())
    hass.http.register_view(FinanceDashboardSetupAuthorizeView())
    hass.http.register_view(FinanceDashboardSetupCompleteView())
    _LOGGER.debug("Finance API endpoints registered")


# ------------------------------------------------------------------
# Setup wizard endpoints (used by panel overlay)
# ------------------------------------------------------------------


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
            return self.json(
                {"configured": False, "has_entry": False}
            )

        configured = entry.data.get("configured", False)
        has_pending_code = bool(
            hass.data.get(DOMAIN, {}).get("pending_auth_code")
        )
        # Include pending session accounts for step 3 of wizard
        pending_accounts = hass.data.get(DOMAIN, {}).get(
            "pending_accounts", []
        )

        result = {
            "configured": configured,
            "has_entry": True,
            "institution_name": entry.data.get(
                "institution_name", ""
            ),
            "account_count": len(entry.data.get("accounts", [])),
            "pending_auth_code": has_pending_code,
            "pending_accounts": pending_accounts,
        }
        return self.json(result)


class FinanceDashboardSetupInstitutionsView(HomeAssistantView):
    """List available banking institutions for DE."""

    url = f"/api/{DOMAIN}/setup/institutions"
    name = f"api:{DOMAIN}:setup_institutions"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Fetch DE bank list from Enable Banking API.

        Always returns HTTP 200 with error details in the body so the
        frontend can inspect error_type reliably.  HA's callApi() throws
        on non-200 responses, swallowing the JSON body.
        """
        hass = request.app["hass"]

        try:
            from .credential_manager import CredentialManager

            cred_mgr = CredentialManager(hass)
            await cred_mgr.async_initialize()
            credentials = await cred_mgr.async_get_api_credentials()

            if not credentials:
                _LOGGER.warning(
                    "No Enable Banking credentials found — "
                    "user must configure the integration first"
                )
                return self.json(
                    {
                        "error": "No API credentials stored",
                        "error_type": "no_credentials",
                    }
                )

            from .enablebanking_client import EnableBankingClient

            client = EnableBankingClient(
                credentials["application_id"],
                credentials["private_key_pem"],
            )

            institutions = await client.async_get_institutions("DE")
            _LOGGER.debug(
                "Fetched %d institutions from Enable Banking",
                len(institutions),
            )
            return self.json({"institutions": institutions})

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout fetching institutions from Enable Banking API")
            return self.json(
                {
                    "error": "Enable Banking API timeout — please try again",
                    "error_type": "timeout",
                }
            )
        except Exception as exc:
            _LOGGER.exception("Failed to fetch institutions")
            error_type = "api_error"
            error_msg = "Failed to fetch institutions"
            exc_msg = str(exc).lower()
            if "401" in exc_msg or "403" in exc_msg or "unauthorized" in exc_msg:
                error_type = "invalid_credentials"
                error_msg = "API credentials rejected by Enable Banking"
            return self.json(
                {"error": error_msg, "error_type": error_type}
            )


class FinanceDashboardSetupAuthorizeView(HomeAssistantView):
    """Initiate bank authorization — returns auth URL for redirect."""

    url = f"/api/{DOMAIN}/setup/authorize"
    name = f"api:{DOMAIN}:setup_authorize"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Start bank auth and return the authorization URL.

        Always returns HTTP 200 so the frontend can read error details.
        """
        hass = request.app["hass"]

        try:
            body = await request.json()
        except Exception:
            return self.json({"error": "Invalid JSON body"})

        institution_name = body.get("institution_name", "")
        if not institution_name:
            return self.json({"error": "institution_name required"})

        try:
            from .credential_manager import CredentialManager

            cred_mgr = CredentialManager(hass)
            await cred_mgr.async_initialize()
            credentials = await cred_mgr.async_get_api_credentials()

            if not credentials:
                return self.json(
                    {"error": "No API credentials stored"}
                )

            from .enablebanking_client import EnableBankingClient

            client = EnableBankingClient(
                credentials["application_id"],
                credentials["private_key_pem"],
            )

            base_url = (
                hass.config.external_url or hass.config.internal_url
            )
            callback_url = (
                f"{base_url}/api/{DOMAIN}/oauth/callback"
            )
            _LOGGER.debug(
                "Auth callback URL: %s (external=%s, internal=%s)",
                callback_url,
                hass.config.external_url,
                hass.config.internal_url,
            )

            valid_until = (
                datetime.now(timezone.utc)
                + timedelta(days=SESSION_MAX_DAYS)
            ).isoformat()

            state = str(uuid.uuid4())

            auth_data = await client.async_create_auth(
                aspsp_name=institution_name,
                aspsp_country="DE",
                redirect_url=callback_url,
                valid_until=valid_until,
                state=state,
            )

            auth_url = auth_data.get("url", "")
            if not auth_url:
                _LOGGER.error(
                    "Enable Banking returned no auth URL: %s",
                    auth_data,
                )
                return self.json(
                    {"error": "No authorization URL received"}
                )

            # Store pending auth for panel flow (not config flow)
            hass.data.setdefault(DOMAIN, {})
            hass.data[DOMAIN]["pending_setup_auth"] = {
                "auth_id": auth_data.get("auth_id", ""),
                "institution_name": institution_name,
                "institution_id": body.get("institution_id", ""),
                "institution_logo": body.get(
                    "institution_logo", ""
                ),
            }
            # Clear any stale auth code
            hass.data[DOMAIN].pop("pending_auth_code", None)
            hass.data[DOMAIN].pop("pending_accounts", None)

            return self.json({"auth_url": auth_url})

        except Exception as exc:
            _LOGGER.exception("Failed to create bank authorization")
            exc_msg = str(exc)
            error_detail = f"Authorization failed: {exc_msg[:300]}"

            # Try to extract structured error from Enable Banking
            import json as _json

            try:
                api_err = _json.loads(exc_msg)
                detail = api_err.get("detail", [])
                if detail:
                    fields = ", ".join(
                        d.get("msg", "") for d in detail
                    )
                    error_detail = (
                        f"Enable Banking: {api_err.get('message', exc_msg)} "
                        f"— {fields}"
                    )
                elif api_err.get("error"):
                    error_detail = (
                        f"Enable Banking: {api_err['error']} "
                        f"— {api_err.get('message', '')}"
                    )
            except (ValueError, TypeError):
                pass

            if "redirect" in exc_msg.lower():
                error_detail = (
                    f"Redirect URL nicht registriert — die Callback-URL "
                    f"'{callback_url}' ist nicht bei Enable Banking "
                    f"hinterlegt."
                )
            return self.json({"error": error_detail})


class FinanceDashboardSetupCompleteView(HomeAssistantView):
    """Complete bank setup — exchange code for session, save accounts."""

    url = f"/api/{DOMAIN}/setup/complete"
    name = f"api:{DOMAIN}:setup_complete"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Finalize setup with account assignments."""
        hass = request.app["hass"]

        try:
            body = await request.json()
        except Exception:
            return self.json(
                {"error": "Invalid JSON body"}, status_code=400
            )

        account_assignments = body.get("accounts", [])

        # Session was already created in OAuth callback
        session_id = hass.data.get(DOMAIN, {}).get(
            "pending_session_id"
        )
        raw_accounts = hass.data.get(DOMAIN, {}).get(
            "pending_accounts", []
        )

        if not session_id or not raw_accounts:
            return self.json(
                {"error": "No pending session — complete bank authorization first"},
                status_code=400,
            )

        pending_auth = hass.data.get(DOMAIN, {}).get(
            "pending_setup_auth", {}
        )

        try:
            from .credential_manager import CredentialManager

            cred_mgr = CredentialManager(hass)
            await cred_mgr.async_initialize()
            credentials = await cred_mgr.async_get_api_credentials()

            if not credentials:
                return self.json(
                    {"error": "No API credentials stored"},
                    status_code=400,
                )

            from .enablebanking_client import EnableBankingClient

            client = EnableBankingClient(
                credentials["application_id"],
                credentials["private_key_pem"],
            )

            if not raw_accounts:
                return self.json(
                    {"error": "No accounts linked"},
                    status_code=400,
                )

            # Fetch details for each account
            account_config = []
            for raw_acc in raw_accounts:
                acc_id = raw_acc.get("id", "")

                # Find user assignment for this account
                assignment = {}
                for a in account_assignments:
                    if a.get("id") == acc_id:
                        assignment = a
                        break

                try:
                    details = await client.async_get_account_details(
                        acc_id
                    )
                    acct = details.get("account", {})
                except Exception:
                    _LOGGER.warning(
                        "Failed to fetch details for account %s",
                        acc_id,
                    )
                    acct = raw_acc

                account_config.append(
                    {
                        "id": acc_id,
                        "iban": acct.get(
                            "iban", raw_acc.get("iban", "")
                        ),
                        "name": acct.get(
                            "name", raw_acc.get("name", "")
                        ),
                        "institution": pending_auth.get(
                            "institution_name", ""
                        ),
                        "institution_id": pending_auth.get(
                            "institution_id", ""
                        ),
                        "logo": pending_auth.get(
                            "institution_logo", ""
                        ),
                        "currency": acct.get(
                            "currency",
                            raw_acc.get("currency", "EUR"),
                        ),
                        "type": assignment.get("type", "personal"),
                        "person": assignment.get("person", ""),
                    }
                )

            # Store session encrypted
            valid_until = (
                datetime.now() + timedelta(days=SESSION_MAX_DAYS)
            ).isoformat()
            if session_id:
                await cred_mgr.async_store_session(
                    session_id, valid_until
                )

            # Update config entry
            entry = hass.data.get(DOMAIN, {}).get("entry")
            if entry:
                institution_name = pending_auth.get(
                    "institution_name", ""
                )
                hass.config_entries.async_update_entry(
                    entry,
                    title=f"Finance ({institution_name})",
                    data={
                        "configured": True,
                        "institution_id": pending_auth.get(
                            "institution_id", ""
                        ),
                        "institution_name": institution_name,
                        "institution_logo": pending_auth.get(
                            "institution_logo", ""
                        ),
                        "session_id": session_id,
                        "accounts": account_config,
                    },
                )

            # Clean up pending state
            hass.data[DOMAIN].pop("pending_auth_code", None)
            hass.data[DOMAIN].pop("pending_setup_auth", None)
            hass.data[DOMAIN].pop("pending_accounts", None)

            # Reload entry to trigger full initialization
            await hass.config_entries.async_reload(entry.entry_id)

            return self.json(
                {
                    "success": True,
                    "account_count": len(account_config),
                }
            )

        except Exception:
            _LOGGER.exception("Failed to complete bank setup")
            return self.json(
                {"error": "Setup completion failed"},
                status_code=502,
            )


# ------------------------------------------------------------------
# OAuth callback (bank redirect)
# ------------------------------------------------------------------


class FinanceDashboardOAuthCallbackView(HomeAssistantView):
    """Handle OAuth callback from Enable Banking bank authorization.

    After the user authorizes at their bank, Enable Banking redirects here
    with a `code` parameter. We store the code and either resume the config
    flow (legacy) or let the panel poll for it (new panel-driven flow).
    """

    url = f"/api/{DOMAIN}/oauth/callback"
    name = f"api:{DOMAIN}:oauth_callback"
    requires_auth = False  # Bank redirect — no HA auth header

    async def get(self, request: web.Request) -> web.Response:
        """Handle GET redirect from bank after authorization."""
        hass = request.app["hass"]

        code = request.query.get("code")
        if code:
            hass.data.setdefault(DOMAIN, {})
            hass.data[DOMAIN]["pending_auth_code"] = code
            _LOGGER.info(
                "OAuth callback received with authorization code"
            )

            # Check if this is a panel-driven flow
            pending_setup = hass.data.get(DOMAIN, {}).get(
                "pending_setup_auth"
            )
            if pending_setup:
                # Panel flow — also fetch accounts for the wizard
                try:
                    from .credential_manager import CredentialManager

                    cred_mgr = CredentialManager(hass)
                    await cred_mgr.async_initialize()
                    credentials = (
                        await cred_mgr.async_get_api_credentials()
                    )

                    if credentials:
                        from .enablebanking_client import (
                            EnableBankingClient,
                        )

                        client = EnableBankingClient(
                            credentials["application_id"],
                            credentials["private_key_pem"],
                        )
                        session_data = (
                            await client.async_create_session(code)
                        )
                        hass.data[DOMAIN]["pending_accounts"] = (
                            session_data.get("accounts", [])
                        )
                        hass.data[DOMAIN]["pending_session_id"] = (
                            session_data.get("session_id", "")
                        )
                except Exception:
                    _LOGGER.exception(
                        "Failed to fetch accounts after OAuth callback"
                    )
            else:
                # Legacy config flow — resume it
                pending_auth = hass.data.get(DOMAIN, {}).get(
                    "pending_auth"
                )
                if pending_auth and "flow_id" in pending_auth:
                    await hass.config_entries.flow.async_configure(
                        flow_id=pending_auth["flow_id"]
                    )
                    _LOGGER.info(
                        "Config flow %s resumed after bank auth",
                        pending_auth["flow_id"],
                    )
        else:
            _LOGGER.warning(
                "OAuth callback received without authorization code"
            )

        html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Finance</title>
<style>
body { font-family: -apple-system, sans-serif; background: #0a0a0f;
  color: #e8e8ed; display: flex; justify-content: center;
  align-items: center; min-height: 100vh; margin: 0; }
.card { background: #12121a; border-radius: 16px; padding: 48px;
  text-align: center; max-width: 400px; border: 1px solid rgba(255,255,255,0.06); }
h1 { color: #4ecca3; font-size: 24px; margin: 0 0 12px; }
p { color: #9898a8; font-size: 14px; line-height: 1.6; }
.icon { font-size: 48px; margin-bottom: 16px; }
</style></head><body>
<div class="card">
  <div class="icon">&#9989;</div>
  <h1>Bankverbindung erfolgreich</h1>
  <p>Dein Bankkonto wurde autorisiert.<br>
  Du kannst diesen Tab schlie&szlig;en und zum Finance zur&uuml;ckkehren.</p>
</div>
</body></html>"""

        return web.Response(
            text=html, content_type="text/html", status=200
        )


# ------------------------------------------------------------------
# Data endpoints (used by dashboard panel)
# ------------------------------------------------------------------


class FinanceDashboardStaticView(HomeAssistantView):
    """Serve static frontend files."""

    url = f"/api/{DOMAIN}/static/{{filename}}"
    name = f"api:{DOMAIN}:static"
    requires_auth = False  # Static JS/CSS files

    async def get(
        self, request: web.Request, filename: str
    ) -> web.Response:
        """Serve a static file from the frontend directory."""
        frontend_dir = Path(__file__).parent / "frontend"
        file_path = frontend_dir / filename

        if not file_path.exists() or not file_path.is_file():
            return web.Response(status=404)

        try:
            file_path.resolve().relative_to(frontend_dir.resolve())
        except ValueError:
            return web.Response(status=403)

        content_type = "application/javascript"
        if filename.endswith(".css"):
            content_type = "text/css"
        elif filename.endswith(".html"):
            content_type = "text/html"

        return web.Response(
            body=file_path.read_bytes(),
            content_type=content_type,
            headers={
                "Cache-Control": "public, max-age=3600",
            },
        )


class FinanceDashboardBalanceView(HomeAssistantView):
    """API endpoint for account balances."""

    url = f"/api/{DOMAIN}/balances"
    name = f"api:{DOMAIN}:balances"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Get balances for all linked accounts."""
        hass = request.app["hass"]
        domain_data = hass.data.get(DOMAIN, {})

        # Find the manager (stored by entry_id)
        manager = None
        for key, val in domain_data.items():
            if key not in ("entry", "pending_auth_code",
                           "pending_setup_auth", "pending_accounts",
                           "pending_session_id"):
                manager = val
                break

        if not manager:
            return self.json(
                {"error": "Not configured"}, status_code=404
            )

        balances = await manager.async_get_balance()

        sanitized = {}
        for account_id, data in balances.items():
            sanitized[account_id] = {
                "account_name": data.get("account_name", "Unknown"),
                "iban_masked": data.get("iban_masked", "****"),
                "institution": data.get("institution", ""),
                "logo": data.get("logo", ""),
                "balances": data.get("balances", []),
            }

        return self.json(sanitized)


class FinanceDashboardTransactionsView(HomeAssistantView):
    """API endpoint for transactions.

    PRIVACY-FIRST: Individual transaction details are only returned
    to HA admin users. Non-admin users receive only aggregated
    category summaries — no individual transaction data.
    """

    url = f"/api/{DOMAIN}/transactions"
    name = f"api:{DOMAIN}:transactions"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Get recent transactions (admin-only detail view)."""
        hass = request.app["hass"]
        domain_data = hass.data.get(DOMAIN, {})

        manager = None
        for key, val in domain_data.items():
            if key not in ("entry", "pending_auth_code",
                           "pending_setup_auth", "pending_accounts",
                           "pending_session_id"):
                manager = val
                break

        if not manager:
            return self.json(
                {"error": "Not configured"}, status_code=404
            )

        user = request.get("hass_user")
        is_admin = user and user.is_admin if user else False

        if not is_admin:
            summary = await manager.async_get_monthly_summary()
            return self.json(
                {
                    "privacy": "aggregate_only",
                    "message": "Individual transactions require admin access.",
                    "categories": summary.get("categories", {}),
                    "total_income": summary.get("total_income", 0),
                    "total_expenses": summary.get(
                        "total_expenses", 0
                    ),
                    "transaction_count": summary.get(
                        "transaction_count", 0
                    ),
                }
            )

        transactions = manager.get_cached_transactions(limit=100)

        sanitized = []
        for txn in transactions:
            sanitized.append(
                {
                    "date": txn.get("bookingDate", ""),
                    "amount": txn.get("transactionAmount", {}).get(
                        "amount", "0"
                    ),
                    "currency": txn.get("transactionAmount", {}).get(
                        "currency", "EUR"
                    ),
                    "description": txn.get(
                        "remittanceInformationUnstructured", ""
                    ),
                    "creditor": txn.get("creditorName", ""),
                    "category": txn.get("category", "other"),
                    "status": txn.get("_status", "booked"),
                }
            )

        return self.json(
            {"privacy": "admin_full", "transactions": sanitized}
        )


class FinanceDashboardSummaryView(HomeAssistantView):
    """API endpoint for monthly summary."""

    url = f"/api/{DOMAIN}/summary"
    name = f"api:{DOMAIN}:summary"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Get monthly spending summary."""
        hass = request.app["hass"]
        domain_data = hass.data.get(DOMAIN, {})

        manager = None
        for key, val in domain_data.items():
            if key not in ("entry", "pending_auth_code",
                           "pending_setup_auth", "pending_accounts",
                           "pending_session_id"):
                manager = val
                break

        if not manager:
            return self.json(
                {"error": "Not configured"}, status_code=404
            )

        summary = await manager.async_get_monthly_summary()
        return self.json(summary)
