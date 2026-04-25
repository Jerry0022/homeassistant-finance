"""Shared helpers for Finance API endpoints.

Provides manager lookup, OAuth state validation, and setup client factory
used across multiple view modules.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# OAuth state token TTL in seconds (10 minutes) — must match manager.py
_OAUTH_STATE_TTL = 600


def _get_manager(hass: HomeAssistant):
    """Find the FinanceDashboardManager in hass.data."""
    domain_data = hass.data.get(DOMAIN, {})
    entry = domain_data.get("entry")
    if entry:
        mgr = domain_data.get(entry.entry_id)
        if mgr is not None:
            return mgr
    # Fallback: scan for manager by type
    from ..manager import FinanceDashboardManager

    for val in domain_data.values():
        if isinstance(val, FinanceDashboardManager):
            return val
    return None


async def _validate_oauth_state(hass: HomeAssistant, state: str) -> bool:
    """Validate and consume an OAuth state token (timing-safe, one-time-use).

    Delegates to the manager when available; falls back to the hass.data
    ``_oauth_states`` dict for fresh-setup flows where no manager exists yet.
    """
    import secrets as _secrets

    manager = _get_manager(hass)
    if manager is not None:
        return await manager.async_validate_oauth_state(state)

    # Fallback: hass.data-backed state store (fresh setup, no manager)
    domain_data = hass.data.get(DOMAIN, {})
    oauth_states: dict = domain_data.get("_oauth_states", {})

    if not oauth_states:
        return False

    # Expire old entries
    now = datetime.now(timezone.utc)
    expired = [
        s for s, created in oauth_states.items()
        if (now - datetime.fromisoformat(created)).total_seconds() > _OAUTH_STATE_TTL
    ]
    for s in expired:
        oauth_states.pop(s, None)

    # Timing-safe match
    matched: str | None = None
    for registered in list(oauth_states.keys()):
        if _secrets.compare_digest(registered, state):
            matched = registered
            oauth_states.pop(registered, None)
            break

    return matched is not None


async def _get_setup_client(hass: HomeAssistant):
    """Return an EnableBankingClient for setup-wizard endpoints.

    Enforces the 4/day ASPSP rate-limit gate before handing back a client.
    If the integration manager already exists the gate is delegated to it;
    otherwise the cached ``rate_limited_until`` timestamp in hass.data is
    checked directly so that the quota cannot be bypassed by re-running the
    wizard.

    Returns:
        EnableBankingClient instance.

    Raises:
        RuntimeError: when rate-limited or credentials are unavailable.
    """
    from ..enablebanking_client import RateLimitExceeded

    # --- Rate-limit gate via manager (preferred) ---
    manager = _get_manager(hass)
    if manager is not None and manager.rate_limited_until:
        raise RateLimitExceeded(
            f"API rate-limited until {manager.rate_limited_until.isoformat()}"
        )

    # --- Credentials ---
    from ..credential_manager import CredentialManager
    from ..enablebanking_client import EnableBankingClient

    cred_mgr = CredentialManager(hass)
    await cred_mgr.async_initialize()
    credentials = await cred_mgr.async_get_api_credentials()

    if not credentials:
        raise RuntimeError("No Enable Banking credentials stored")

    return EnableBankingClient(
        credentials["application_id"],
        credentials["private_key_pem"],
        session=async_get_clientsession(hass),
    )
