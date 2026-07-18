"""Diagnostics/transparency endpoint for Finance.

Cache-read endpoint — never hits the banking API. Unbounded calls safe.

Provides:
- FinanceDashboardDiagnosticsView — full cache snapshot (accounts, banks,
  entity hints, rate-limit + refresh stats) consumed by the fd-diagnostics
  transparency widget and the fd-state-banner advisory banner.
"""

from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from ..const import DOMAIN
from ._helpers import _get_manager

_LOGGER = logging.getLogger(__name__)


class FinanceDashboardDiagnosticsView(HomeAssistantView):
    """API endpoint for the transparency/diagnostics widget."""

    url = f"/api/{DOMAIN}/diagnostics"
    name = f"api:{DOMAIN}:diagnostics"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Return a cache-only diagnostics snapshot."""
        hass = request.app["hass"]
        manager = _get_manager(hass)

        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)

        return self.json(manager.get_diagnostics())
