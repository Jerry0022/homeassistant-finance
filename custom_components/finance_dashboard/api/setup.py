"""Setup-wizard HTTP endpoints for Finance.

Covers the full bank-connection wizard: status check, HA-user listing,
institution search, authorization initiation, OAuth callback, setup
completion, and account-settings update.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from aiohttp import web

from homeassistant.components.http import HomeAssistantView

from ..const import DOMAIN, SESSION_MAX_DAYS
from ._helpers import _get_manager, _get_setup_client, _validate_oauth_state

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

        # Sanitize account details for frontend (no raw IBANs)
        raw_accounts = entry.data.get("accounts", [])
        safe_accounts = []
        for acc in raw_accounts:
            iban = acc.get("iban", "")
            safe_accounts.append({
                "id": acc.get("id", ""),
                "name": acc.get("name", ""),
                "custom_name": acc.get("custom_name", ""),
                "iban_masked": (
                    f"****{iban[-4:]}" if len(iban) >= 4 else "****"
                ),
                "institution": acc.get("institution", ""),
                "institution_id": acc.get("institution_id", ""),
                "logo": acc.get("logo", ""),
                "type": acc.get("type", "personal"),
                "ha_users": acc.get("ha_users", []),
                "person": acc.get("person", ""),
            })

        # Surface any error from the OAuth callback so the wizard can
        # stop polling and display a meaningful message instead of timing
        # out after 5 minutes.
        setup_error = hass.data.get(DOMAIN, {}).get("pending_setup_error")

        result = {
            "configured": configured,
            "has_entry": True,
            "institution_name": entry.data.get(
                "institution_name", ""
            ),
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
        """Fetch DE bank list from Enable Banking API.

        Always returns HTTP 200 with error details in the body so the
        frontend can inspect error_type reliably.  HA's callApi() throws
        on non-200 responses, swallowing the JSON body.
        """
        hass = request.app["hass"]

        try:
            from ..enablebanking_client import RateLimitExceeded

            client = await _get_setup_client(hass)
            institutions = await client.async_get_institutions("DE")
            _LOGGER.debug(
                "Fetched %d institutions from Enable Banking",
                len(institutions),
            )
            return self.json({"institutions": institutions})

        except RateLimitExceeded as exc:
            return self.json(
                {
                    "error": str(exc),
                    "error_type": "rate_limited",
                }
            )
        except RuntimeError as exc:
            error_msg = str(exc)
            _LOGGER.warning("Setup client error: %s", error_msg)
            return self.json(
                {
                    "error": error_msg,
                    "error_type": "no_credentials",
                }
            )
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
            from ..enablebanking_client import RateLimitExceeded

            client = await _get_setup_client(hass)

            # Build callback URL from the request origin — this
            # ensures the URL matches how the user actually accesses
            # HA (Nabu Casa, local HTTPS, etc.) rather than relying
            # on hass.config which may be stale or "Automatic".
            base_url = f"{request.scheme}://{request.host}"
            callback_url = (
                f"{base_url}/api/{DOMAIN}/oauth/callback"
            )
            _LOGGER.info(
                "Auth callback URL: %s (from request origin)",
                callback_url,
            )

            # Enable Banking demands the redirect URL is pre-registered
            # in the application dashboard. Hard-fail early with a
            # helpful message so the user knows what to fix instead of
            # waiting 5 min for the wizard to time out.
            if request.scheme != "https":
                return self.json({
                    "error": (
                        "Bank-Autorisierung erfordert HTTPS. Aktuelle "
                        f"Callback-URL '{callback_url}' ist HTTP — "
                        "öffne das Finance-Panel über die HTTPS-URL "
                        "deiner HA-Instanz (z. B. Nabu Casa) oder "
                        "richte ein TLS-Zertifikat ein."
                    ),
                    "error_type": "callback_not_https",
                    "callback_url": callback_url,
                })

            valid_until = (
                datetime.now(timezone.utc)
                + timedelta(days=SESSION_MAX_DAYS)
            ).isoformat()

            state = str(uuid.uuid4())

            # Register the state token for CSRF validation in the callback.
            # If no manager is available (fresh setup) we fall back to storing
            # the state in hass.data so the callback can still validate it.
            manager = _get_manager(hass)
            if manager is not None:
                await manager.async_register_oauth_state(state)
            else:
                hass.data.setdefault(DOMAIN, {})
                hass.data[DOMAIN].setdefault("_oauth_states", {})[state] = (
                    datetime.now(timezone.utc).isoformat()
                )

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
            # Clear any stale auth code / error from previous attempts
            hass.data[DOMAIN].pop("pending_auth_code", None)
            hass.data[DOMAIN].pop("pending_accounts", None)
            hass.data[DOMAIN].pop("pending_setup_error", None)

            return self.json({"auth_url": auth_url})

        except RuntimeError as exc:
            # Credentials missing — surface cleanly without stack trace
            return self.json({"error": str(exc), "error_type": "no_credentials"})
        except Exception as exc:
            from ..enablebanking_client import RateLimitExceeded as _RLE
            if isinstance(exc, _RLE):
                return self.json({"error": str(exc), "error_type": "rate_limited"})
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
            from ..enablebanking_client import RateLimitExceeded

            client = await _get_setup_client(hass)

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

                # Build person field: from HA users or free text
                ha_users = assignment.get("ha_users", [])
                person = assignment.get("person", "")
                if ha_users and not person:
                    person = ", ".join(
                        u.get("name", "") for u in ha_users
                    )

                account_config.append(
                    {
                        "id": acc_id,
                        "iban": acct.get(
                            "iban", raw_acc.get("iban", "")
                        ),
                        "name": acct.get(
                            "name", raw_acc.get("name", "")
                        ),
                        "custom_name": assignment.get(
                            "custom_name", ""
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
                        "person": person,
                        "ha_users": ha_users,
                    }
                )

            # Store session encrypted
            from ..credential_manager import CredentialManager

            cred_mgr = CredentialManager(hass)
            await cred_mgr.async_initialize()

            valid_until = (
                datetime.now() + timedelta(days=SESSION_MAX_DAYS)
            ).isoformat()
            if session_id:
                await cred_mgr.async_store_session(
                    session_id, valid_until
                )

            # Update config entry — merge with existing data to
            # preserve accounts from previously connected banks.
            entry = hass.data.get(DOMAIN, {}).get("entry")
            if entry:
                institution_name = pending_auth.get(
                    "institution_name", ""
                )
                institution_id = pending_auth.get(
                    "institution_id", ""
                )

                # Merge accounts: keep existing accounts from other
                # banks, replace accounts that share the same
                # institution_id (re-auth of same bank).
                existing_accounts = list(entry.data.get("accounts", []))
                existing_accounts = [
                    acc for acc in existing_accounts
                    if acc.get("institution_id") != institution_id
                ]
                merged_accounts = existing_accounts + account_config

                # Build multi-bank title
                bank_names = sorted({
                    acc.get("institution", "")
                    for acc in merged_accounts
                    if acc.get("institution")
                })
                title = (
                    f"Finance ({', '.join(bank_names)})"
                    if bank_names
                    else f"Finance ({institution_name})"
                )

                # Merge sessions: store one session_id per bank
                existing_sessions = dict(
                    entry.data.get("sessions", {})
                )
                existing_sessions[institution_id] = session_id

                hass.config_entries.async_update_entry(
                    entry,
                    title=title,
                    data={
                        **entry.data,
                        "configured": True,
                        "institution_id": institution_id,
                        "institution_name": institution_name,
                        "institution_logo": pending_auth.get(
                            "institution_logo", ""
                        ),
                        "session_id": session_id,
                        "sessions": existing_sessions,
                        "accounts": merged_accounts,
                    },
                )

            # Clean up pending state
            hass.data[DOMAIN].pop("pending_auth_code", None)
            hass.data[DOMAIN].pop("pending_setup_auth", None)
            hass.data[DOMAIN].pop("pending_accounts", None)

            # Schedule entry reload in the background so the
            # response reaches the frontend before unload kills
            # the HTTP endpoints.  The frontend polls /setup/status
            # until configured=true after the reload completes.
            # After reload, trigger ONE live refresh so the newly
            # created entities are populated with real bank data
            # immediately — without this the user sees "unavailable"
            # (cache is empty on first setup) until they click
            # "Aktualisieren". This is a single user-initiated call
            # (completing the setup wizard counts), NOT a periodic
            # auto-refresh, so it stays inside the 4/day policy.
            async def _deferred_reload() -> None:
                import asyncio as _aio

                await _aio.sleep(1)
                try:
                    await hass.config_entries.async_reload(
                        entry.entry_id
                    )
                except Exception:
                    _LOGGER.exception("Deferred entry reload failed")
                    return
                try:
                    domain_data = hass.data.get(DOMAIN, {})
                    new_manager = domain_data.get(entry.entry_id)
                    coordinator = domain_data.get(
                        f"{entry.entry_id}_coordinator"
                    )
                    if new_manager is not None:
                        # Explicit live fetch — the setup wizard click
                        # is the user-initiated trigger. Populates both
                        # transactions and balances in one round.
                        await new_manager.async_refresh_transactions()
                    if coordinator is not None:
                        # Push the fresh cache through the coordinator so
                        # all entities pick up the new values at once.
                        await coordinator.async_refresh()
                    _LOGGER.info(
                        "Initial post-setup refresh completed"
                    )
                except Exception:
                    _LOGGER.exception(
                        "Initial post-setup refresh failed"
                    )

            hass.async_create_task(_deferred_reload())

            return self.json(
                {
                    "success": True,
                    "account_count": len(account_config),
                }
            )

        except Exception:
            _LOGGER.exception("Failed to complete bank setup")
            return self.json({"error": "Setup completion failed"})


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
            return self.json(
                {"error": "Not configured"}, status_code=404
            )

        try:
            body = await request.json()
        except Exception:
            return self.json(
                {"error": "Invalid JSON body"}, status_code=400
            )

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
        hass.config_entries.async_update_entry(
            entry, data=new_data
        )

        # Update manager if running
        manager = _get_manager(hass)
        if manager:
            manager._accounts = existing

        _LOGGER.info(
            "Updated account settings for %d accounts",
            len(updates),
        )
        return self.json({"success": True})


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

        # --- CSRF: validate state parameter before processing code ---
        state_param = request.query.get("state", "")
        if state_param:
            state_valid = await _validate_oauth_state(hass, state_param)
            if not state_valid:
                _LOGGER.error(
                    "OAuth callback rejected: invalid or expired state parameter"
                )
                return self.json(
                    {"ok": False, "error": "invalid_state"}, status_code=400
                )
        else:
            _LOGGER.warning(
                "OAuth callback received without state parameter — "
                "possible CSRF or direct-link access"
            )

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
                # Panel flow — also fetch accounts for the wizard.
                # On failure, store the error so /setup/status can
                # surface it to the wizard (which polls until it sees
                # either pending_accounts OR setup_error).
                try:
                    client = await _get_setup_client(hass)
                    session_data = await client.async_create_session(code)
                    accounts = session_data.get("accounts", [])
                    if not accounts:
                        hass.data[DOMAIN]["pending_setup_error"] = (
                            "Bank hat keine Konten zurückgegeben. "
                            "Bitte Bankvertrag/Konsent prüfen."
                        )
                    else:
                        hass.data[DOMAIN]["pending_accounts"] = accounts
                        hass.data[DOMAIN]["pending_session_id"] = (
                            session_data.get("session_id", "")
                        )
                except Exception as exc:
                    from ..enablebanking_client import RateLimitExceeded
                    if isinstance(exc, RateLimitExceeded):
                        hass.data[DOMAIN]["pending_setup_error"] = (
                            f"API-Tageslimit erreicht: {exc}"
                        )
                    elif isinstance(exc, RuntimeError):
                        hass.data[DOMAIN]["pending_setup_error"] = (
                            "Keine API-Credentials gespeichert — "
                            "Integration neu einrichten."
                        )
                    else:
                        _LOGGER.exception(
                            "Failed to fetch accounts after OAuth callback"
                        )
                        hass.data[DOMAIN]["pending_setup_error"] = (
                            f"Session-Erstellung fehlgeschlagen: "
                            f"{str(exc)[:300]}"
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
