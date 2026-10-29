"""Refresh HTTP endpoints for Finance.

Provides:
- RefreshTriggerView  — user-triggered live bank fetch (POST /refresh)
- RefreshStatusView   — cache-only status polling (GET /refresh_status)
"""

from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from ..const import DOMAIN, EXPLICIT_IMPORT_TRIGGER
from ._helpers import _get_manager

_LOGGER = logging.getLogger(__name__)


class FinanceDashboardRefreshStatusView(HomeAssistantView):
    """Cache-only refresh status — safe for unbounded polling.

    Returns the snapshot produced by ``manager.get_refresh_status()``.
    Used by the frontend to poll while a refresh is in flight and to
    render cache-age + last-stats in the header without ever hitting
    the banking API.
    """

    url = f"/api/{DOMAIN}/refresh_status"
    name = f"api:{DOMAIN}:refresh_status"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Return the current refresh snapshot (no API calls)."""
        hass = request.app["hass"]
        manager = _get_manager(hass)

        if not manager:
            return self.json(
                {
                    "is_refreshing": False,
                    "has_cache": False,
                    "error": "Not configured",
                }
            )

        return self.json(manager.get_refresh_status())


class FinanceDashboardRefreshTriggerView(HomeAssistantView):
    """Explicit user-triggered refresh — the ONLY allowed live-fetch entry.

    Blocks while the refresh is in flight and returns the final stats,
    so the frontend can show a single "5 Konten, 243 Transaktionen"
    toast instead of polling guesswork. Hard Rule: only invoked on
    user-initiated actions (refresh button, manual service call).
    """

    url = f"/api/{DOMAIN}/refresh"
    name = f"api:{DOMAIN}:refresh"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Run a refresh and return the stats when it finishes."""
        hass = request.app["hass"]

        # R9: live bank fetches are admin-only — only admins may consume the
        # 4/day rate limit.  Non-admin users can still read cached data via
        # /balances, /summary, /transactions (aggregate view).
        user = request.get("hass_user")
        if not user or not user.is_admin:
            return self.json({"ok": False, "error": "admin_required"}, status_code=403)

        manager = _get_manager(hass)

        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)

        # Server-side fetch-trigger gate.  Imports are rate limited and must
        # not be a side effect of page views, so the bank is only called when
        # the request states it is the explicit "Neu importieren" action.  A
        # bare POST (e.g. an automatic call on panel open) is refused before
        # any client is touched.
        if not await _is_explicit_import(request):
            return self.json(
                {
                    "ok": False,
                    "reason": "explicit_trigger_required",
                    "status": manager.get_refresh_status(),
                },
                status_code=400,
            )

        # Forward PSU IP from the originating request so Enable Banking can
        # include it in audit trails as required by PSD2 RTS.  ``request.remote``
        # is the direct-connection IP; when behind a proxy the real IP may be
        # in X-Forwarded-For, but we intentionally use only the direct value
        # to avoid header-injection spoofing.
        psu_ip: str | None = getattr(request, "remote", None)

        # Short-circuit when already rate-limited so the UI can show a clear
        # message instead of waiting for an HTTP 429 round-trip.  This gate
        # applies to background calls only: with a PSU IP the request carries
        # PSU headers, which makes it attended, and PSD2 RTS Art. 36(5)(b)
        # caps only unattended access.  Gating the button the user just
        # pressed would refuse a call the bank actually permits.
        if manager.rate_limited_until and not psu_ip:
            return self.json(
                {
                    "ok": False,
                    "reason": "rate_limited",
                    "status": manager.get_refresh_status(),
                }
            )

        try:
            await manager.async_refresh_transactions(psu_ip=psu_ip)
        except Exception as exc:
            _LOGGER.exception("Refresh trigger failed")
            return self.json(
                {
                    "ok": False,
                    "reason": "error",
                    "message": str(exc)[:200],
                    "status": manager.get_refresh_status(),
                }
            )

        # Also push fresh data through the coordinator so entity states
        # update in lockstep with the user's click.
        domain_data = hass.data.get(DOMAIN, {})
        entry = domain_data.get("entry")
        if entry:
            coordinator = domain_data.get(f"{entry.entry_id}_coordinator")
            if coordinator:
                try:
                    await coordinator.async_refresh()
                except Exception:
                    _LOGGER.exception("Coordinator refresh after live fetch failed")

        status = manager.get_refresh_status()
        return self.json({"ok": True, "status": status})


async def _is_explicit_import(request: web.Request) -> bool:
    """True only when the JSON body carries ``{"trigger": "user_import"}``."""
    try:
        body = await request.json()
    except Exception:
        return False
    return isinstance(body, dict) and body.get("trigger") == EXPLICIT_IMPORT_TRIGGER


class FinanceDashboardReprocessView(HomeAssistantView):
    """"Aktualisieren": rebuild everything from the stored raw data.

    Never calls the bank and never touches the fetch budget.
    """

    url = f"/api/{DOMAIN}/reprocess"
    name = f"api:{DOMAIN}:reprocess"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Replay the raw archive, re-derive, push the coordinator."""
        hass = request.app["hass"]
        user = request.get("hass_user")
        if not user or not user.is_admin:
            return self.json({"ok": False, "error": "admin_required"}, status_code=403)
        manager = _get_manager(hass)
        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)

        try:
            stats = await manager.async_reprocess_and_derive()
        except Exception as exc:
            _LOGGER.exception("Reprocess failed")
            return self.json({"ok": False, "reason": "error", "message": str(exc)[:200]})

        domain_data = hass.data.get(DOMAIN, {})
        entry = domain_data.get("entry")
        coordinator = domain_data.get(f"{entry.entry_id}_coordinator") if entry else None
        if coordinator:
            try:
                await coordinator.async_refresh()
            except Exception:
                _LOGGER.exception("Coordinator refresh after reprocess failed")

        ok = stats.get("outcome") in ("rebuilt", "empty")
        return self.json({"ok": ok, "stats": stats})


class FinanceDashboardFreshnessView(HomeAssistantView):
    """Cache-only data freshness, import log and monthly validity."""

    url = f"/api/{DOMAIN}/freshness"
    name = f"api:{DOMAIN}:freshness"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Admins get the full report, everyone else ``as_of`` / ``last_import``."""
        hass = request.app["hass"]
        manager = _get_manager(hass)
        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)
        user = request.get("hass_user")
        admin = bool(user and user.is_admin)
        return self.json(manager.get_freshness(admin=admin))
