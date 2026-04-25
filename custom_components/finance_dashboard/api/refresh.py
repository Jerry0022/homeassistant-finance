"""Refresh HTTP endpoints for Finance.

Provides:
- RefreshTriggerView  — user-triggered live bank fetch (POST /refresh)
- RefreshStatusView   — cache-only status polling (GET /refresh_status)
"""

from __future__ import annotations

import logging

from aiohttp import web

from homeassistant.components.http import HomeAssistantView

from ..const import DOMAIN
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
            return self.json(
                {"ok": False, "error": "admin_required"}, status_code=403
            )

        manager = _get_manager(hass)

        if not manager:
            return self.json(
                {"error": "Not configured"}, status_code=404
            )

        # Short-circuit when already rate-limited so the UI can show a
        # clear message instead of waiting for an HTTP 429 round-trip.
        if manager.rate_limited_until:
            return self.json(
                {
                    "ok": False,
                    "reason": "rate_limited",
                    "status": manager.get_refresh_status(),
                }
            )

        # Forward PSU IP from the originating request so Enable Banking can
        # include it in audit trails as required by PSD2 RTS.  ``request.remote``
        # is the direct-connection IP; when behind a proxy the real IP may be
        # in X-Forwarded-For, but we intentionally use only the direct value
        # to avoid header-injection spoofing.
        psu_ip: str | None = getattr(request, "remote", None)
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
            coordinator = domain_data.get(
                f"{entry.entry_id}_coordinator"
            )
            if coordinator:
                try:
                    await coordinator.async_refresh()
                except Exception:
                    _LOGGER.exception(
                        "Coordinator refresh after live fetch failed"
                    )

        status = manager.get_refresh_status()
        return self.json({"ok": True, "status": status})
