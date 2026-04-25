"""Demo mode endpoints for Finance.

Provides:
- DemoToggleView  — toggle demo mode on/off (admin only)
- DemoDataView    — return a fresh demo dataset (no manager required)
"""

from __future__ import annotations

import logging

from aiohttp import web

from homeassistant.components.http import HomeAssistantView

from ..const import DOMAIN
from ._helpers import _get_manager

_LOGGER = logging.getLogger(__name__)


class FinanceDashboardDemoToggleView(HomeAssistantView):
    """Toggle demo mode on/off (admin only)."""

    url = f"/api/{DOMAIN}/demo/toggle"
    name = f"api:{DOMAIN}:demo_toggle"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Toggle demo mode and return new state."""
        hass = request.app["hass"]

        user = request.get("hass_user")
        is_admin = user and user.is_admin if user else False
        if not is_admin:
            return self.json(
                {"error": "Admin access required"},
                status_code=403,
            )

        manager = _get_manager(hass)

        if not manager:
            # Without a manager, demo mode has no meaning — there is no
            # coordinator to push into, no entities to update, and no
            # persistence path. Return 503 so the frontend can guide the
            # user to complete the setup wizard first.
            return self.json(
                {"error": "Not configured"}, status_code=503
            )

        enabled = not manager.demo_mode
        manager.set_demo_mode(enabled)

        # Persist to entry.options so demo survives HA restarts
        entry = hass.data.get(DOMAIN, {}).get("entry")
        if entry:
            new_options = {**entry.options, "demo_mode": enabled}
            hass.config_entries.async_update_entry(
                entry, options=new_options
            )

        # Trigger coordinator refresh so entities update
        domain_data = hass.data.get(DOMAIN, {})
        coordinator = (
            domain_data.get(f"{entry.entry_id}_coordinator")
            if entry
            else None
        )
        if coordinator:
            await coordinator.async_refresh()
        return self.json({"demo_mode": enabled})


class FinanceDashboardDemoDataView(HomeAssistantView):
    """Return demo data — works with or without a config entry."""

    url = f"/api/{DOMAIN}/demo/data"
    name = f"api:{DOMAIN}:demo_data"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Return a fresh demo dataset."""
        from ..demo import generate_demo_data

        data = generate_demo_data()
        # Strip internal keys
        data.pop("_demo_accounts", None)
        data.pop("_demo_transactions", None)
        data.pop("_demo_balances", None)
        return self.json(data)
