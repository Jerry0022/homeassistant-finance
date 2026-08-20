"""Shared helpers for Finance API endpoints.

Provides manager lookup, OAuth state validation, and setup client factory
used across multiple view modules.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# OAuth state token TTL in seconds (10 minutes) — must match manager.py
_OAUTH_STATE_TTL = 600

# hass.data key for global (manager-independent) rate-limit timestamp
_GLOBAL_RATE_LIMIT_KEY = "_global_rate_limit_until"


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


def _parse_utc_dt(ts: str) -> datetime:
    """Parse an ISO timestamp as UTC-aware datetime.

    If the parsed datetime is naive (no tzinfo), UTC is assumed.
    This guards against mixed naive/aware comparisons (F3).
    """
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


async def _register_oauth_state(hass: HomeAssistant, state: str) -> None:
    """Register an OAuth state token in BOTH stores.

    Writes to the manager's ``_oauth_states`` dict when a manager exists,
    and ALWAYS also writes to ``hass.data[DOMAIN]["_oauth_states"]`` as a
    cross-reload fallback (F1).  This way a manager reload between
    authorize and callback cannot cause spurious invalid_state rejections.
    """
    now_iso = datetime.now(UTC).isoformat()

    # Always write to hass.data fallback store
    hass.data.setdefault(DOMAIN, {})
    states_dict: dict = hass.data[DOMAIN].setdefault("_oauth_states", {})

    # F5: bound the dict — if > 32 entries, evict the 16 oldest
    if len(states_dict) >= 32:
        sorted_states = sorted(states_dict.items(), key=lambda kv: kv[1])
        for old_key, _ in sorted_states[:16]:
            states_dict.pop(old_key, None)

    states_dict[state] = now_iso

    # Also write to manager when available
    manager = _get_manager(hass)
    if manager is not None:
        await manager.async_register_oauth_state(state)


async def _validate_oauth_state(hass: HomeAssistant, state: str) -> bool:
    """Validate and consume an OAuth state token (timing-safe, one-time-use).

    Checks BOTH the manager store AND hass.data store so that a manager
    reload between the authorize and callback steps cannot produce a false
    invalid_state rejection (F1).  On a successful match the state is
    removed from BOTH stores (one-time-use guarantee).
    """
    import secrets as _secrets

    now = datetime.now(UTC)

    # --- 1. Try manager store first ---
    manager = _get_manager(hass)
    manager_matched = False
    if manager is not None:
        manager_matched = await manager.async_validate_oauth_state(state)
        if manager_matched:
            # Also purge from hass.data to keep stores consistent
            domain_data = hass.data.get(DOMAIN, {})
            domain_data.get("_oauth_states", {}).pop(state, None)
            return True

    # --- 2. Fallback: hass.data store ---
    domain_data = hass.data.get(DOMAIN, {})
    oauth_states: dict = domain_data.get("_oauth_states", {})

    if not oauth_states:
        return False

    # Expire old entries
    expired = [
        s
        for s, created in list(oauth_states.items())
        if (now - _parse_utc_dt(created)).total_seconds() > _OAUTH_STATE_TTL
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


async def _get_setup_client(hass: HomeAssistant, *, enforce_rate_limit: bool = True):
    """Return an EnableBankingClient for setup-wizard endpoints.

    Enforces the 4/day ASPSP rate-limit gate before handing back a client.
    Checks BOTH the manager rate-limit state (when available) AND the
    persistent ``hass.data`` global rate-limit timestamp so that a
    fresh-setup flow (manager=None) cannot bypass the quota gate (F2).

    Args:
        enforce_rate_limit: Set to False for calls that do not touch an
            ASPSP.  The ``/aspsps`` catalog is served by Enable Banking
            itself, not by a bank, so it neither spends nor is bound by
            the per-ASPSP quota — gating it would lock a rate-limited
            user out of connecting any new bank at all.

    Returns:
        EnableBankingClient instance.

    Raises:
        RateLimitExceeded: when the API is still rate-limited and the gate
            is enforced.
        RuntimeError: when credentials are unavailable.
    """
    from ..enablebanking_client import RateLimitExceeded

    if enforce_rate_limit:
        # --- Rate-limit gate via manager (preferred) ---
        manager = _get_manager(hass)
        if manager is not None and manager.rate_limited_until:
            raise RateLimitExceeded(
                f"API rate-limited until {manager.rate_limited_until.isoformat()}"
            )

        # --- Rate-limit gate via persistent hass.data (fresh-setup fallback, F2) ---
        domain_data = hass.data.get(DOMAIN, {})
        global_rl = domain_data.get(_GLOBAL_RATE_LIMIT_KEY)
        if global_rl:
            try:
                rl_dt = _parse_utc_dt(global_rl)
                now = datetime.now(UTC)
                if rl_dt > now:
                    raise RateLimitExceeded(
                        f"API rate-limited until {rl_dt.isoformat()} "
                        "— bitte morgen erneut versuchen."
                    )
            except (ValueError, TypeError):
                # Corrupt timestamp — clear it and proceed
                domain_data.pop(_GLOBAL_RATE_LIMIT_KEY, None)

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


# ---------------------------------------------------------------------------
# Institution catalog cache
# ---------------------------------------------------------------------------
# The DE bank list changes rarely but the wizard is useless without it.
# Persisting it means an Enable Banking outage degrades the wizard to a
# stale list instead of an empty one.


def _institution_store(hass: HomeAssistant):
    """Return the Store holding the cached institution catalog."""
    from homeassistant.helpers.storage import Store

    from ..const import STORAGE_KEY_INSTITUTIONS, STORAGE_VERSION

    domain_data = hass.data.setdefault(DOMAIN, {})
    store = domain_data.get("_institution_store")
    if store is None:
        store = Store(hass, STORAGE_VERSION, STORAGE_KEY_INSTITUTIONS)
        domain_data["_institution_store"] = store
    return store


async def async_load_cached_institutions(hass: HomeAssistant) -> tuple[list, str | None]:
    """Load the cached catalog.

    Returns:
        ``(institutions, cached_at_iso)``.  Empty list + None when no usable
        cache exists.
    """
    try:
        data = await _institution_store(hass).async_load()
    except Exception:  # noqa: BLE001 — a corrupt cache must never break setup
        _LOGGER.warning("Institution cache unreadable — ignoring it")
        return [], None

    if not isinstance(data, dict):
        return [], None
    institutions = data.get("institutions") or []
    if not isinstance(institutions, list) or not institutions:
        return [], None
    return institutions, data.get("cached_at")


async def async_save_cached_institutions(hass: HomeAssistant, institutions: list) -> None:
    """Persist a freshly fetched catalog. Never raises."""
    if not institutions:
        return
    try:
        await _institution_store(hass).async_save(
            {
                "institutions": institutions,
                "cached_at": datetime.now(UTC).isoformat(),
            }
        )
    except Exception:  # noqa: BLE001 — caching is best-effort
        _LOGGER.debug("Could not persist institution cache", exc_info=True)


def _cache_is_fresh(cached_at: str | None) -> bool:
    """True when the cache timestamp is within the configured TTL."""
    if not cached_at:
        return False
    from ..const import INSTITUTION_CACHE_TTL_HOURS

    try:
        age = datetime.now(UTC) - _parse_utc_dt(cached_at)
    except (ValueError, TypeError):
        return False
    return age.total_seconds() < INSTITUTION_CACHE_TTL_HOURS * 3600
