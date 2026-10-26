"""Bank-connect helpers shared by the subentry flow and the repairs fix flow.

Enable Banking authorization is a PSU redirect: ``POST /auth`` yields a bank
URL, the bank redirects back with ``?code=&state=``, ``POST /sessions``
exchanges the code.  This module owns everything around that which is not UI:

* the redirect URL (``my.home-assistant.io`` when available),
* the signed ``state`` (same format as HA core's OAuth2 helper),
* a bridge that lets core's ``/auth/external/callback`` view resume a
  *subentry* flow (core only knows the main flow manager),
* the post-session test call and the IBAN-derived account identity.

Secrets (session id, full IBANs) never leave this module except into the
credential store.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .account_identity import identity_key
from .const import SESSION_MAX_DAYS

_LOGGER = logging.getLogger(__name__)

# Same constants HA core's config_entry_oauth2_flow uses.
AUTH_CALLBACK_PATH = "/auth/external/callback"
MY_REDIRECT_URL = "https://my.home-assistant.io/redirect/oauth"
_DATA_JWT_SECRET = "oauth2_jwt_secret"  # shared with core so its view can decode our state
_BRIDGE_FLAG = "_finance_callback_bridge"


class ConnectError(Exception):
    """A bank-connect step failed; ``reason`` is a translation key."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------------------
# Redirect URL + state
# ---------------------------------------------------------------------------


def get_redirect_url(hass: HomeAssistant) -> str:
    """Return the redirect URL that must be registered at Enable Banking.

    ``my.home-assistant.io`` is preferred: it is stable no matter under which
    host HA is reached (the redirect is resolved in the user's browser).
    Fallback when the ``my`` integration is not loaded: HA's external, else
    internal URL plus core's callback path.  Returns "" if no URL is known.
    """
    if "my" in hass.config.components:
        return MY_REDIRECT_URL
    try:
        base = get_url(hass, prefer_external=True)
    except NoURLAvailableError:
        return ""
    return f"{base}{AUTH_CALLBACK_PATH}"


def encode_state(hass: HomeAssistant, flow_id: str, redirect_uri: str) -> str:
    """Signed state carrying the flow id (HA core compatible, HS256 JWT)."""
    secret = hass.data.get(_DATA_JWT_SECRET)
    if secret is None:
        secret = hass.data[_DATA_JWT_SECRET] = secrets.token_hex()
    return jwt.encode({"flow_id": flow_id, "redirect_uri": redirect_uri}, secret, algorithm="HS256")


def install_callback_bridge(hass: HomeAssistant) -> None:
    """Let core's ``/auth/external/callback`` resume subentry flows.

    Core's callback view calls ``hass.config_entries.flow.async_configure``
    with the flow id from the state JWT.  Subentry flows live in a separate
    manager (``hass.config_entries.subentries``), so core raises UnknownFlow.
    We wrap ``async_configure`` once: on UnknownFlow for an id that belongs to
    a subentry flow, the call is delegated.  Idempotent; lost on HA restart,
    which is fine because flows do not survive a restart either.
    """
    flow_mgr = hass.config_entries.flow
    if getattr(flow_mgr, _BRIDGE_FLAG, False):
        return
    from homeassistant.data_entry_flow import UnknownFlow

    original = flow_mgr.async_configure

    async def _configure(flow_id: str, user_input: Any = None) -> Any:
        try:
            return await original(flow_id, user_input)
        except UnknownFlow:
            subentries = getattr(hass.config_entries, "subentries", None)
            if subentries is None:
                raise
            subentries.async_get(flow_id)  # raises UnknownFlow if not ours
            return await subentries.async_configure(flow_id, user_input)

    flow_mgr.async_configure = _configure
    setattr(flow_mgr, _BRIDGE_FLAG, True)


# ---------------------------------------------------------------------------
# Enable Banking calls
# ---------------------------------------------------------------------------


async def async_credentials(hass: HomeAssistant):
    """Initialised credential manager."""
    from .credential_manager import CredentialManager

    cred = CredentialManager(hass)
    await cred.async_initialize()
    return cred


async def async_build_client(hass: HomeAssistant):
    """Client from stored API credentials (no quota gate: setup is attended)."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .enablebanking_client import EnableBankingClient

    cred = await async_credentials(hass)
    credentials = await cred.async_get_api_credentials()
    if not credentials:
        raise ConnectError("no_credentials")
    return EnableBankingClient(
        credentials["application_id"],
        credentials["private_key_pem"],
        session=async_get_clientsession(hass),
    )


def map_exception(exc: Exception) -> ConnectError:
    """Translate API exceptions into a user-facing reason key."""
    import aiohttp

    from .enablebanking_client import RateLimitExceeded

    if isinstance(exc, ConnectError):
        return exc
    if isinstance(exc, RateLimitExceeded):
        return ConnectError("rate_limited")
    if isinstance(exc, aiohttp.ClientResponseError):
        if exc.status in (401, 403):
            return ConnectError("invalid_credentials")
        return ConnectError("bank_error")
    if isinstance(exc, aiohttp.ClientError | TimeoutError):
        return ConnectError("connection_failed")
    return ConnectError("unknown")


def default_valid_until() -> str:
    return (datetime.now(UTC) + timedelta(days=SESSION_MAX_DAYS)).isoformat()


async def async_start_authorization(
    hass: HomeAssistant,
    client: Any,
    flow_id: str,
    aspsp_name: str,
    aspsp_country: str,
) -> tuple[str, str]:
    """POST /auth; returns (bank_url, valid_until)."""
    redirect = get_redirect_url(hass)
    if not redirect:
        raise ConnectError("no_url_available")
    valid_until = default_valid_until()
    try:
        auth = await client.async_create_auth(
            aspsp_name=aspsp_name,
            aspsp_country=aspsp_country,
            redirect_url=redirect,
            valid_until=valid_until,
            state=encode_state(hass, flow_id, redirect),
        )
    except Exception as exc:
        raise map_exception(exc) from exc
    url = auth.get("url", "")
    if not url:
        raise ConnectError("bank_error")
    return url, valid_until


async def async_complete_session(client: Any, code: str) -> dict[str, Any]:
    """POST /sessions; returns {"session_id", "accounts"}. Never logs values."""
    try:
        session = await client.async_create_session(code)
    except Exception as exc:
        raise map_exception(exc) from exc
    if not session.get("session_id"):
        raise ConnectError("bank_error")
    if not session.get("accounts"):
        raise ConnectError("no_accounts")
    return session


async def async_probe_accounts(
    client: Any, aspsp_name: str, accounts: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Test call per account; returns subentry-safe ``[{uid, identity_key}]``."""
    refs, _records = await async_probe_account_records(client, aspsp_name, accounts)
    return refs


async def async_probe_account_records(
    client: Any, aspsp_name: str, accounts: list[dict[str, Any]]
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Test call per account; returns ``(subentry refs, full account records)``.

    The refs (``{uid, identity_key}``) go into the subentry, which must not
    carry account numbers.  The records are what the manager fetches from —
    they go into the entry's ``accounts`` list.  Both share one identity, so
    the subentry finds its accounts again.

    A rate limit on the test call must not block linking (the session is
    already valid): it falls back to the IBAN from the session response.
    Any other failure aborts so a broken link is never persisted.
    """
    from .enablebanking_client import RateLimitExceeded

    refs: list[dict[str, str]] = []
    records: list[dict[str, Any]] = []
    for raw in accounts:
        uid = raw.get("id", "")
        iban = raw.get("iban", "")
        try:
            details = await client.async_get_account_details(uid)
            iban = (details.get("account") or {}).get("iban") or iban
        except RateLimitExceeded:
            _LOGGER.info("Account test call rate-limited; using session data for identity")
        except Exception as exc:
            raise map_exception(exc) from exc
        record: dict[str, Any] = {
            "id": uid,
            "iban": iban,
            "name": raw.get("name", ""),
            "currency": raw.get("currency", "EUR"),
            "institution": aspsp_name,
            "institution_id": aspsp_name,
        }
        for field in ("identification", "account_type"):
            if raw.get(field):
                record[field] = raw[field]
        record["key"] = identity_key(record)
        records.append(record)
        refs.append({"uid": uid, "identity_key": record["key"]})
    return refs, records
